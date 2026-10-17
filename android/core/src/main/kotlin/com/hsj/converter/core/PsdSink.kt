package com.hsj.converter.core

import java.io.BufferedOutputStream
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.io.OutputStream
import java.nio.ByteBuffer
import java.nio.channels.FileChannel
import java.nio.file.StandardOpenOption
import java.util.Arrays
import kotlin.math.max
import kotlin.math.min

data class PsdLayerSpec(
    val name: String,
    val opacity: Float,
    val visible: Boolean,
    val blendMode: Int,
    val clipping: Boolean,
    val lockAlpha: Boolean,
)

/**
 * Streaming PSD writer. Layer channel data is encoded into a staging file as layers are
 * decoded, so no all-layer pixel set is ever held in memory.
 */
class PsdSink(
    private val output: File,
    private val width: Int,
    private val height: Int,
    private val ppi: Int,
    private val workDir: File,
) {
    private data class Record(
        val spec: PsdLayerSpec,
        val bounds: RgbaRect,
        val channelLengths: IntArray,
    )

    private val records = ArrayList<Record>()
    private val stagingFile = File(workDir, "psd_channels.bin")
    private val staging = FileChannel.open(
        stagingFile.toPath(),
        StandardOpenOption.CREATE,
        StandardOpenOption.READ,
        StandardOpenOption.WRITE,
    )
    private var stagingPos = 0L
    private var tempIndex = 0

    init {
        require(width in 1..30000 && height in 1..30000) {
            "PSD 不支持 ${width}x$height（上限 30000）"
        }
        output.parentFile?.mkdirs()
        staging.truncate(0)
    }

    fun addLayer(
        spec: PsdLayerSpec,
        surface: MappedRgbaSurface?,
        bounds: RgbaRect?,
        constant: IntArray? = null,
    ) {
        require(records.size < 30000) { "图层数量过多" }
        val crop = if (bounds != null && !bounds.isEmpty) bounds else RgbaRect(0, 0, 1, 1)
        val lengths = encodeLayer(surface, crop, constant)
        records += Record(spec, crop, lengths)
    }

    private fun encodeLayer(
        surface: MappedRgbaSurface?,
        crop: RgbaRect,
        constant: IntArray?,
    ): IntArray {
        val rows = crop.height
        val cols = crop.width
        val files = (0 until 4).map { File(workDir, "psd_${tempIndex}_$it.bin") }
        tempIndex++
        val channels = files.map {
            FileChannel.open(
                it.toPath(),
                StandardOpenOption.CREATE,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE,
            ).also { ch -> ch.truncate(0) }
        }
        val rowLengths = Array(4) { IntArray(rows) }
        val rgba = ByteArray(width * 4)
        val planes = Array(4) { ByteArray(cols) }
        val zeros = ByteArray(rows * 2)
        channels.forEach {
            it.write(ByteBuffer.wrap(zeros))
            it.position(rows * 2L)
        }

        try {
            for (y in 0 until rows) {
                if (surface != null) {
                    surface.readRow(crop.top + y, rgba)
                    for (c in 0 until 4) {
                        var src = crop.left * 4 + c
                        val plane = planes[c]
                        for (x in 0 until cols) {
                            plane[x] = rgba[src]
                            src += 4
                        }
                    }
                } else if (constant != null) {
                    for (c in 0 until 4) Arrays.fill(planes[c], constant[c].toByte())
                } else {
                    for (c in 0 until 4) Arrays.fill(planes[c], 0)
                }

                for (c in 0 until 4) {
                    val enc = PackBits.encode(planes[c], 0, cols)
                    if (enc.size > 0xFFFF) throw HsjException("RLE 行过长，无法写入 PSD")
                    rowLengths[c][y] = enc.size
                    channels[c].write(ByteBuffer.wrap(enc))
                }
            }

            for (c in 0 until 4) {
                val counts = ByteBuffer.allocate(rows * 2)
                for (y in 0 until rows) counts.putShort(rowLengths[c][y].toShort())
                counts.flip()
                channels[c].write(counts, 0)
            }

            val result = IntArray(4)
            for (c in 0 until 4) {
                val size = channels[c].size()
                staging.position(stagingPos)
                staging.write(ByteBuffer.wrap(byteArrayOf(0, 1)))
                stagingPos += 2
                var transferred = 0L
                channels[c].position(0)
                while (transferred < size) {
                    val n = channels[c].transferTo(transferred, size - transferred, staging)
                    if (n <= 0) break
                    transferred += n
                }
                stagingPos += transferred
                result[c] = (2 + transferred).toInt()
            }
            return result
        } finally {
            channels.forEach { runCatching { it.close() } }
            files.forEach { runCatching { it.delete() } }
        }
    }

    fun finish(composite: MappedRgbaSurface) {
        require(composite.width == width && composite.height == height)
        val recordsBytes = ByteArrayOutputStream()
        for (record in records) recordsBytes.write(buildRecord(record))
        val channelBytes = staging.size()
        val expected = records.sumOf { it.channelLengths.sumOf { v -> v.toLong() } }
        if (channelBytes != expected) {
            throw HsjException("PSD channel staging 长度不一致")
        }
        var layerInfoLength = 2L + recordsBytes.size() + channelBytes
        val pad = if (layerInfoLength % 2L != 0L) 1 else 0
        layerInfoLength += pad
        val sectionLength = 4L + layerInfoLength + 4L

        val resources = resolutionResource(ppi)

        FileOutputStream(output).use { fos ->
            val buffered = BufferedOutputStream(fos, 256 * 1024)
            val out = DataOutputStream(buffered)
            out.writeBytes("8BPS")
            out.writeShort(1)
            repeat(6) { out.writeByte(0) }
            out.writeShort(4)
            out.writeInt(height)
            out.writeInt(width)
            out.writeShort(8)
            out.writeShort(3)
            out.writeInt(0) // color mode data

            out.writeInt(resources.size)
            out.write(resources)

            out.writeInt(sectionLength.toInt())
            out.writeInt(layerInfoLength.toInt())
            out.writeShort(records.size)
            out.write(recordsBytes.toByteArray())
            copyChannel(staging, channelBytes, out)
            if (pad == 1) out.writeByte(0)

            out.writeInt(0) // global layer mask info length
            out.writeShort(1) // merged image RLE compression
            writeMergedImage(composite, out)
            out.flush()
        }
        closeStaging()
    }

    private fun writeMergedImage(
        composite: MappedRgbaSurface,
        out: DataOutputStream,
    ) {
        val files = (0 until 4).map { File(workDir, "merged_${tempIndex}_$it.bin") }
        tempIndex++
        val channels = files.map {
            FileChannel.open(
                it.toPath(),
                StandardOpenOption.CREATE,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE,
            ).also { ch -> ch.truncate(0) }
        }
        val rowLengths = Array(4) { IntArray(height) }
        val rgba = ByteArray(width * 4)
        val planes = Array(4) { ByteArray(width) }
        try {
            for (y in 0 until height) {
                composite.readRow(y, rgba)
                for (c in 0 until 4) {
                    var src = c
                    val plane = planes[c]
                    for (x in 0 until width) {
                        plane[x] = rgba[src]
                        src += 4
                    }
                }
                for (c in 0 until 4) {
                    val enc = PackBits.encode(planes[c], 0, width)
                    if (enc.size > 0xFFFF) throw HsjException("合并预览 RLE 行过长")
                    rowLengths[c][y] = enc.size
                    channels[c].write(ByteBuffer.wrap(enc))
                }
            }
            val counts = ByteBuffer.allocate(height * 4 * 2)
            for (c in 0 until 4) {
                for (y in 0 until height) counts.putShort(rowLengths[c][y].toShort())
            }
            counts.flip()
            out.write(counts.array())

            for (c in 0 until 4) {
                copyChannel(channels[c], channels[c].size(), out)
            }
        } finally {
            channels.forEach { runCatching { it.close() } }
            files.forEach { runCatching { it.delete() } }
        }
    }

    private fun buildRecord(record: Record): ByteArray {
        val spec = record.spec
        val extra = ByteArrayOutputStream()
        val extraOut = DataOutputStream(extra)
        extraOut.writeInt(0) // layer mask
        extraOut.writeInt(0) // blending ranges
        extraOut.write(pascalName(spec.name))
        extraOut.write(luniBlock(spec.name))
        if (extra.size() % 2 != 0) extra.write(0)

        val bytes = ByteArrayOutputStream()
        val o = DataOutputStream(bytes)
        val b = record.bounds
        o.writeInt(b.top)
        o.writeInt(b.left)
        o.writeInt(b.bottom)
        o.writeInt(b.right)
        o.writeShort(4)
        val channelIds = intArrayOf(0, 1, 2, -1)
        for (c in 0 until 4) {
            o.writeShort(channelIds[c])
            o.writeInt(record.channelLengths[c])
        }
        o.writeBytes("8BIM")
        o.writeBytes(BlendModes.psdKey(spec.blendMode))
        val opacity = Math.rint((spec.opacity.coerceIn(0f, 1f) * 255f).toDouble())
            .toInt().coerceIn(0, 255)
        var flags = 0x08
        if (!spec.visible) flags = flags or 0x02
        if (spec.lockAlpha) flags = flags or 0x01
        o.writeByte(opacity)
        o.writeByte(if (spec.clipping) 1 else 0)
        o.writeByte(flags)
        o.writeByte(0)
        o.writeInt(extra.size())
        o.write(extra.toByteArray())
        if (bytes.size() % 2 != 0) bytes.write(0)
        return bytes.toByteArray()
    }

    private fun resolutionResource(ppi: Int): ByteArray {
        if (ppi <= 0) return ByteArray(0)
        val fixed = Math.round(ppi * 65536.0).toInt()
        val data = ByteBuffer.allocate(16)
            .putInt(fixed).putShort(1).putShort(1)
            .putInt(fixed).putShort(1).putShort(1)
            .array()
        val block = ByteArrayOutputStream()
        val b = DataOutputStream(block)
        b.writeBytes("8BIM")
        b.writeShort(1005)
        b.writeShort(0)
        b.writeInt(data.size)
        b.write(data)
        var bytes = block.toByteArray()
        if (bytes.size % 2 != 0) bytes += 0
        return bytes
    }

    private fun pascalName(name: String): ByteArray {
        val encoded = name.toByteArray(Charsets.UTF_8)
        val raw = encoded.copyOf(min(255, encoded.size))
        val data = ByteArray(1 + raw.size)
        data[0] = raw.size.toByte()
        raw.copyInto(data, 1)
        val padded = if (data.size % 4 == 0) data else data + ByteArray(4 - data.size % 4)
        return padded
    }

    private fun luniBlock(name: String): ByteArray {
        val uni = name.toByteArray(Charsets.UTF_16BE)
        var payload = ByteArray(4 + uni.size)
        val buf = ByteBuffer.wrap(payload)
        buf.putInt(uni.size / 2)
        buf.put(uni)
        payload = buf.array()
        if (payload.size % 2 != 0) payload += 0
        val block = ByteArrayOutputStream()
        val b = DataOutputStream(block)
        b.writeBytes("8BIM")
        b.writeBytes("luni")
        b.writeInt(payload.size)
        b.write(payload)
        return block.toByteArray()
    }

    private fun copyChannel(channel: FileChannel, length: Long, out: OutputStream) {
        channel.position(0)
        val buffer = ByteBuffer.allocate(256 * 1024)
        var remaining = length
        while (remaining > 0) {
            buffer.clear()
            buffer.limit(min(buffer.capacity().toLong(), remaining).toInt())
            val n = channel.read(buffer)
            if (n <= 0) break
            out.write(buffer.array(), 0, n)
            remaining -= n
        }
    }

    private fun closeStaging() {
        runCatching { staging.close() }
        runCatching { stagingFile.delete() }
    }

    fun abort() {
        closeStaging()
        runCatching { output.delete() }
    }
}
