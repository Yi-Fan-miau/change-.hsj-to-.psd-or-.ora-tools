package com.hsj.converter.core

import java.io.BufferedInputStream
import java.io.Closeable
import java.io.File
import java.io.FileOutputStream
import java.io.InputStream
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.channels.FileChannel
import java.nio.file.StandardOpenOption
import java.util.zip.ZipFile

/**
 * Random-access view over the inner .hsj container(s).
 *
 * The outer ZIP is extracted to a temporary container file so layer data can be read
 * strip-by-strip without loading the whole draft into memory.
 */
class HsjArchive private constructor(
    val folderName: String,
    val files: LinkedHashMap<String, FileRange>,
    private val channels: Map<File, FileChannel>,
    private val tempFiles: List<File>,
) : Closeable {

    companion object {
        private val MAGIC = byteArrayOf(0x38, 0x45, 0x39, 0x45, 0x32, 0x33, 0x44, 0x46)

        fun open(input: File, workDir: File): HsjArchive {
            require(input.isFile) { "输入文件不存在" }
            workDir.mkdirs()
            val tempFiles = ArrayList<File>()
            val containerFiles = ArrayList<File>()
            try {
                val first = ByteArray(8)
                RandomAccessFile(input, "r").use { raf ->
                    if (raf.length() >= 8) raf.readFully(first)
                }
                if (first.contentEquals(MAGIC)) {
                    containerFiles += input
                } else if (first[0] == 'P'.code.toByte() && first[1] == 'K'.code.toByte()) {
                    ZipFile(input).use { zip ->
                        var index = 0
                        val entries = zip.entries()
                        while (entries.hasMoreElements()) {
                            val entry = entries.nextElement()
                            if (entry.isDirectory) continue
                            zip.getInputStream(entry).use { stream ->
                                val buffered = if (stream is BufferedInputStream) stream
                                else BufferedInputStream(stream, 64 * 1024)
                                val head = ByteArray(8)
                                var n = 0
                                while (n < 8) {
                                    val r = buffered.read(head, n, 8 - n)
                                    if (r <= 0) break
                                    n += r
                                }
                                if (n == 8 && head.contentEquals(MAGIC)) {
                                    val outFile = File(workDir, "container_${index++}.bin")
                                    tempFiles += outFile
                                    FileOutputStream(outFile).use { out ->
                                        out.write(head)
                                        buffered.copyTo(out, 128 * 1024)
                                    }
                                    containerFiles += outFile
                                }
                            }
                        }
                    }
                }
                if (containerFiles.isEmpty()) {
                    throw HsjException("不是有效的 .hsj 文件：未找到 8E9E23DF 容器")
                }

                val channels = LinkedHashMap<File, FileChannel>()
                val files = LinkedHashMap<String, FileRange>()
                var folderName = ""
                var firstContainer = true

                for (file in containerFiles) {
                    val channel = FileChannel.open(file.toPath(), StandardOpenOption.READ)
                    channels[file] = channel
                    val size = channel.size()
                    if (size < 0xC8) throw HsjException("容器文件过短")
                    val header = readFully(channel, 0, 0xC8)
                    if (!header.copyOfRange(0, 8).contentEquals(MAGIC)) {
                        throw HsjException("容器魔数不正确")
                    }
                    val footerOffset = beLong(header, 0x14)
                    val footerLength = beLong(header, 0x1C)
                    if (footerOffset < 36 || footerLength < 0 || footerLength > 64L * 1024 * 1024 ||
                        footerOffset + footerLength > size
                    ) {
                        throw HsjException("容器 footer 范围无效")
                    }
                    val footer = readFully(channel, footerOffset, footerLength.toInt())
                    val (name, entries) = parseFooter(footer)
                    if (firstContainer) {
                        folderName = name
                        firstContainer = false
                    }
                    for ((path, offset, length) in entries) {
                        if (length <= 0 || offset < 0 || offset + length > size) continue
                        files[path] = FileRange(file, offset, length)
                    }
                }

                return HsjArchive(folderName, files, channels, tempFiles)
            } catch (t: Throwable) {
                tempFiles.forEach { it.delete() }
                throw t
            }
        }

        private fun parseFooter(buf: ByteArray): Pair<String, List<Triple<String, Long, Long>>> {
            var folder = ""
            val entries = ArrayList<Triple<String, Long, Long>>()
            val reader = ProtoReader(buf, 0, buf.size)
            while (true) {
                val field = reader.next() ?: break
                when {
                    field.number == 1 && field.wireType == 2 ->
                        folder = String(field.bytes!!, Charsets.UTF_8)
                    field.number == 12 && field.wireType == 2 -> {
                        var path = ""
                        var offset = 0L
                        var length = 0L
                        val sub = ProtoReader(field.bytes!!, 0, field.bytes.size)
                        while (true) {
                            val f = sub.next() ?: break
                            when {
                                f.number == 1 && f.wireType == 2 ->
                                    path = String(f.bytes!!, Charsets.UTF_8)
                                f.number == 2 && f.wireType == 0 -> offset = f.varint
                                f.number == 3 && f.wireType == 0 -> length = f.varint
                            }
                        }
                        path = path.trimStart('/')
                        if (path.isNotEmpty()) entries += Triple(path, offset, length)
                    }
                }
            }
            return folder to entries
        }

        private fun readFully(channel: FileChannel, position: Long, length: Int): ByteArray {
            if (length < 0) throw HsjException("读取长度无效")
            val out = ByteArray(length)
            val buf = ByteBuffer.wrap(out)
            var pos = position
            while (buf.hasRemaining()) {
                val n = channel.read(buf, pos)
                if (n <= 0) throw HsjException("文件被截断")
                pos += n
            }
            return out
        }
    }

    fun range(name: String): FileRange? {
        val normalized = name.trimStart('/')
        for ((path, range) in files) {
            if (path == normalized || path.endsWith("/$normalized")) return range
        }
        return null
    }

    fun readFile(name: String): ByteArray? {
        val range = range(name) ?: return null
        if (range.length > 512L * 1024 * 1024) throw HsjException("文件过大：$name")
        return readRange(range, 0, range.length.toInt())
    }

    fun readRange(range: FileRange, relativeOffset: Long, length: Int): ByteArray {
        if (relativeOffset < 0 || length < 0 || relativeOffset + length > range.length) {
            throw HsjException("文件范围越界")
        }
        val channel = channels[range.file] ?: throw HsjException("容器未打开")
        return readFully(channel, range.offset + relativeOffset, length)
    }

    fun openRange(range: FileRange, relativeOffset: Long = 0, length: Long = range.length): InputStream {
        if (relativeOffset < 0 || length < 0 || relativeOffset + length > range.length) {
            throw HsjException("文件范围越界")
        }
        val channel = channels[range.file] ?: throw HsjException("容器未打开")
        return RangeInputStream(channel, range.offset + relativeOffset, length)
    }

    fun layerRange(layerId: String): FileRange? = range("layers/$layerId")

    fun layerIds(): List<String> {
        val out = ArrayList<String>()
        for (path in files.keys) {
            if (!path.startsWith("layers/")) continue
            val rest = path.removePrefix("layers/")
            if (rest.isEmpty() || rest.contains('/') || rest == "sellayer") continue
            out += rest
        }
        return out
    }

    override fun close() {
        channels.values.forEach { runCatching { it.close() } }
        tempFiles.forEach { runCatching { it.delete() } }
    }

    private class RangeInputStream(
        private val channel: FileChannel,
        private val start: Long,
        private var remaining: Long,
    ) : InputStream() {
        private var pos = start
        private val one = ByteArray(1)

        override fun read(): Int {
            val n = read(one, 0, 1)
            return if (n <= 0) -1 else one[0].toInt() and 0xFF
        }

        override fun read(b: ByteArray, off: Int, len: Int): Int {
            if (remaining <= 0) return -1
            if (len == 0) return 0
            val count = minOf(len.toLong(), remaining, 1L shl 20).toInt()
            val buffer = ByteBuffer.wrap(b, off, count)
            var read = 0
            while (buffer.hasRemaining()) {
                val n = channel.read(buffer, pos + read)
                if (n <= 0) break
                read += n
            }
            if (read <= 0) return -1
            pos += read
            remaining -= read
            return read
        }
    }
}
