package com.hsj.converter.core

import java.io.Closeable
import java.io.File
import java.io.RandomAccessFile
import java.nio.MappedByteBuffer
import java.nio.channels.FileChannel

data class RgbaRect(val left: Int, val top: Int, val right: Int, val bottom: Int) {
    val width: Int get() = right - left
    val height: Int get() = bottom - top
    val isEmpty: Boolean get() = width <= 0 || height <= 0
}

/** Full-canvas RGBA8 surface backed by a memory-mapped file (straight alpha). */
class MappedRgbaSurface(
    val file: File,
    val width: Int,
    val height: Int,
) : Closeable {
    val byteSize: Long = width.toLong() * height * 4L
    private val raf: RandomAccessFile
    private val channel: FileChannel
    private val map: MappedByteBuffer

    init {
        require(width > 0 && height > 0) { "画布尺寸无效" }
        require(byteSize <= Int.MAX_VALUE.toLong()) { "画布过大，无法映射" }
        file.parentFile?.mkdirs()
        raf = RandomAccessFile(file, "rw")
        raf.setLength(byteSize)
        channel = raf.channel
        map = channel.map(FileChannel.MapMode.READ_WRITE, 0, byteSize)
    }

    fun clear() {
        val zeros = ByteArray(64 * 1024)
        var pos = 0L
        while (pos < byteSize) {
            val n = minOf(zeros.size.toLong(), byteSize - pos).toInt()
            map.position(pos.toInt())
            map.put(zeros, 0, n)
            pos += n
        }
    }

    fun putRow(x: Int, y: Int, src: ByteArray, srcOffset: Int, byteCount: Int) {
        if (y < 0 || y >= height || x < 0 || x >= width) return
        val count = minOf(byteCount, (width - x) * 4)
        if (count <= 0) return
        val position = (y.toLong() * width + x) * 4
        map.position(position.toInt())
        map.put(src, srcOffset, count)
    }

    fun readRow(y: Int, dst: ByteArray, dstOffset: Int = 0) {
        val position = y.toLong() * width * 4
        map.position(position.toInt())
        map.get(dst, dstOffset, width * 4)
    }

    fun writeRow(y: Int, src: ByteArray, srcOffset: Int = 0) {
        val position = y.toLong() * width * 4
        map.position(position.toInt())
        map.put(src, srcOffset, width * 4)
    }

    fun alphaAt(x: Int, y: Int): Int {
        if (x < 0 || x >= width || y < 0 || y >= height) return 0
        val index = (y.toLong() * width + x) * 4 + 3
        return map.get(index.toInt()).toInt() and 0xFF
    }

    /** Bounding box of nonzero alpha, or null if fully transparent. */
    fun alphaBounds(): RgbaRect? {
        var minX = width
        var minY = height
        var maxX = -1
        var maxY = -1
        val row = ByteArray(width * 4)
        for (y in 0 until height) {
            readRow(y, row)
            var first = -1
            var last = -1
            var i = 3
            while (i < row.size) {
                if (row[i].toInt() != 0) {
                    if (first < 0) first = (i - 3) / 4
                    last = (i - 3) / 4
                }
                i += 4
            }
            if (first >= 0) {
                if (y < minY) minY = y
                if (y > maxY) maxY = y
                if (first < minX) minX = first
                if (last > maxX) maxX = last
            }
        }
        if (maxX < 0) return null
        return RgbaRect(minX, minY, maxX + 1, maxY + 1)
    }

    fun sha256(): String {
        val digest = java.security.MessageDigest.getInstance("SHA-256")
        val row = ByteArray(width * 4)
        for (y in 0 until height) {
            readRow(y, row)
            digest.update(row)
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    fun writeAlphaTo(target: MappedAlphaSurface) {
        require(target.width == width && target.height == height)
        val row = ByteArray(width * 4)
        val alpha = ByteArray(width)
        for (y in 0 until height) {
            readRow(y, row)
            var i = 3
            var x = 0
            while (x < width) {
                alpha[x] = row[i]
                x++
                i += 4
            }
            target.writeRow(y, alpha)
        }
    }

    /** Multiplies the alpha channel by base alpha / 255. Used by ORA clipping bake. */
    fun multiplyAlphaBy(base: MappedAlphaSurface) {
        require(base.width == width && base.height == height)
        val row = ByteArray(width * 4)
        val baseRow = ByteArray(width)
        for (y in 0 until height) {
            readRow(y, row)
            base.readRow(y, baseRow)
            var i = 3
            var x = 0
            while (x < width) {
                val a = row[i].toInt() and 0xFF
                if (a != 0) {
                    row[i] = ((a * (baseRow[x].toInt() and 0xFF)) / 255).toByte()
                }
                x++
                i += 4
            }
            writeRow(y, row)
        }
    }

    override fun close() {
        runCatching { channel.close() }
        runCatching { raf.close() }
        file.deleteOnExit()
    }
}

/** Single-channel alpha plane backed by a memory-mapped file. */
class MappedAlphaSurface(
    val file: File,
    val width: Int,
    val height: Int,
) : Closeable {
    val byteSize: Long = width.toLong() * height
    private val raf: RandomAccessFile
    private val channel: FileChannel
    private val map: MappedByteBuffer

    init {
        require(width > 0 && height > 0)
        require(byteSize <= Int.MAX_VALUE.toLong()) { "alpha 平面过大" }
        file.parentFile?.mkdirs()
        raf = RandomAccessFile(file, "rw")
        raf.setLength(byteSize)
        channel = raf.channel
        map = channel.map(FileChannel.MapMode.READ_WRITE, 0, byteSize)
    }

    fun writeRow(y: Int, src: ByteArray, srcOffset: Int = 0) {
        map.position(y * width)
        map.put(src, srcOffset, width)
    }

    fun readRow(y: Int, dst: ByteArray, dstOffset: Int = 0) {
        map.position(y * width)
        map.get(dst, dstOffset, width)
    }

    fun alphaAt(x: Int, y: Int): Int {
        if (x < 0 || x >= width || y < 0 || y >= height) return 0
        return map.get(y * width + x).toInt() and 0xFF
    }

    override fun close() {
        runCatching { channel.close() }
        runCatching { raf.close() }
        file.deleteOnExit()
    }
}
