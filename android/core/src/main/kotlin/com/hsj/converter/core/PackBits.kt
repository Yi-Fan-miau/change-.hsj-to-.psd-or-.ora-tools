package com.hsj.converter.core

import java.io.ByteArrayOutputStream
import kotlin.math.max
import kotlin.math.min

/** PSD PackBits RLE encoder, matching hsjconv/psd.py's heuristic. */
object PackBits {
    fun encode(row: ByteArray, offset: Int, length: Int): ByteArray {
        if (length <= 0) return ByteArray(0)

        var changes = 0
        for (i in 1 until length) {
            if (row[offset + i] != row[offset + i - 1]) changes++
        }
        if (changes + 1 > max(8, length / 8)) {
            val out = ByteArrayOutputStream(length + length / 128 + 1)
            var start = 0
            while (start < length) {
                val n = min(128, length - start)
                out.write(n - 1)
                out.write(row, offset + start, n)
                start += n
            }
            return out.toByteArray()
        }

        val out = ByteArrayOutputStream(length + 16)
        var litStart = 0
        var pos = 0
        while (pos < length) {
            val value = row[offset + pos]
            var end = pos + 1
            while (end < length && row[offset + end] == value) end++
            val runLength = end - pos
            if (runLength >= 3) {
                flushLiterals(out, row, offset, litStart, pos)
                var remaining = runLength
                val v = value.toInt() and 0xFF
                while (remaining > 0) {
                    val take = min(remaining, 128)
                    out.write((257 - take) and 0xFF)
                    out.write(v)
                    remaining -= take
                }
                litStart = end
            }
            pos = end
        }
        flushLiterals(out, row, offset, litStart, length)
        return out.toByteArray()
    }

    private fun flushLiterals(
        out: ByteArrayOutputStream,
        row: ByteArray,
        rowOffset: Int,
        from: Int,
        until: Int,
    ) {
        var a = from
        while (a < until) {
            val b = min(a + 128, until)
            out.write(b - a - 1)
            out.write(row, rowOffset + a, b - a)
            a = b
        }
    }
}
