package com.hsj.converter.core

import java.nio.charset.Charset

internal class ProtoReader(
    private val buf: ByteArray,
    private var pos: Int,
    private val end: Int,
) {
    data class Field(
        val number: Int,
        val wireType: Int,
        val varint: Long = 0L,
        val bytes: ByteArray? = null,
    )

    fun next(): Field? {
        if (pos >= end) return null
        val tag = readVarint()
        val number = (tag ushr 3).toInt()
        val wire = (tag and 7L).toInt()
        if (number == 0) throw HsjException("protobuf 字段号为 0")
        return when (wire) {
            0 -> Field(number, wire, varint = readVarint())
            1 -> {
                requireAvailable(8)
                val raw = buf.copyOfRange(pos, pos + 8)
                pos += 8
                Field(number, wire, bytes = raw)
            }
            2 -> {
                val length = readVarint()
                if (length < 0 || length > Int.MAX_VALUE) {
                    throw HsjException("protobuf 长度字段过大")
                }
                val n = length.toInt()
                requireAvailable(n)
                val raw = buf.copyOfRange(pos, pos + n)
                pos += n
                Field(number, wire, bytes = raw)
            }
            5 -> {
                requireAvailable(4)
                val raw = buf.copyOfRange(pos, pos + 4)
                pos += 4
                Field(number, wire, bytes = raw)
            }
            else -> throw HsjException("不支持的 protobuf wire type: $wire")
        }
    }

    private fun readVarint(): Long {
        var result = 0L
        var shift = 0
        while (true) {
            if (pos >= end) throw HsjException("protobuf varint 被截断")
            val b = buf[pos].toInt() and 0xFF
            pos++
            result = result or ((b and 0x7F).toLong() shl shift)
            if (b and 0x80 == 0) return result
            shift += 7
            if (shift > 63) throw HsjException("protobuf varint 过长")
        }
    }

    private fun requireAvailable(count: Int) {
        if (count < 0 || pos + count > end) {
            throw HsjException("protobuf 字段被截断")
        }
    }
}

internal fun decodeText(raw: ByteArray): String {
    if (raw.isEmpty()) return ""
    for (charset in listOf(Charsets.UTF_8, Charset.forName("GBK"))) {
        try {
            return strictDecode(raw, charset)
        } catch (_: Exception) {
            // try next encoding
        }
    }
    return String(raw, Charsets.ISO_8859_1)
}

private fun strictDecode(raw: ByteArray, charset: Charset): String {
    val decoder = charset.newDecoder()
        .onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
        .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT)
    return decoder.decode(java.nio.ByteBuffer.wrap(raw)).toString()
}

internal fun floatLe(raw: ByteArray): Float {
    if (raw.size < 4) return 0f
    val bits = (raw[0].toInt() and 0xFF) or
        ((raw[1].toInt() and 0xFF) shl 8) or
        ((raw[2].toInt() and 0xFF) shl 16) or
        ((raw[3].toInt() and 0xFF) shl 24)
    return Float.fromBits(bits)
}

internal fun asInt32(value: Long): Int = value.toInt()

internal fun beInt(bytes: ByteArray, offset: Int): Int =
    ((bytes[offset].toInt() and 0xFF) shl 24) or
        ((bytes[offset + 1].toInt() and 0xFF) shl 16) or
        ((bytes[offset + 2].toInt() and 0xFF) shl 8) or
        (bytes[offset + 3].toInt() and 0xFF)

internal fun beLong(bytes: ByteArray, offset: Int): Long {
    var value = 0L
    for (i in 0 until 8) {
        value = (value shl 8) or (bytes[offset + i].toLong() and 0xFF)
    }
    return value
}
