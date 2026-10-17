package com.hsj.converter.core

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

/** Straight-alpha compositor matching hsjconv/blend.py. */
class Compositor {
    private val blended = FloatArray(3)
    private val hsl = FloatArray(3)
    private val hsl2 = FloatArray(3)

    fun fillBackground(composite: MappedRgbaSurface, rgba: IntArray) {
        val row = ByteArray(composite.width * 4)
        var i = 0
        while (i < row.size) {
            row[i] = rgba[0].toByte()
            row[i + 1] = rgba[1].toByte()
            row[i + 2] = rgba[2].toByte()
            row[i + 3] = rgba[3].toByte()
            i += 4
        }
        for (y in 0 until composite.height) composite.writeRow(y, row)
    }

    fun blendLayer(
        composite: MappedRgbaSurface,
        layer: MappedRgbaSurface,
        bounds: RgbaRect?,
        opacity: Float,
        blendMode: Int,
        clipAlpha: MappedAlphaSurface?,
        clipBaseVisible: Boolean,
    ) {
        if (bounds == null || bounds.isEmpty || opacity <= 0f) return
        if (!clipBaseVisible) return
        val left = bounds.left.coerceIn(0, composite.width - 1)
        val right = bounds.right.coerceIn(0, composite.width)
        val top = bounds.top.coerceIn(0, composite.height - 1)
        val bottom = bounds.bottom.coerceIn(0, composite.height)
        if (left >= right || top >= bottom) return

        val dst = ByteArray(composite.width * 4)
        val src = ByteArray(composite.width * 4)
        val baseAlpha = if (clipAlpha != null) ByteArray(composite.width) else null
        val op = opacity.coerceIn(0f, 1f)

        for (y in top until bottom) {
            composite.readRow(y, dst)
            layer.readRow(y, src)
            if (clipAlpha != null) clipAlpha.readRow(y, baseAlpha!!)
            var idx = left * 4
            val end = right * 4
            while (idx < end) {
                val sa = src[idx + 3].toInt() and 0xFF
                if (sa == 0) {
                    idx += 4
                    continue
                }
                var srcAlpha = (sa / 255f) * op
                if (baseAlpha != null) {
                    val ca = baseAlpha[idx / 4].toInt() and 0xFF
                    srcAlpha *= ca / 255f
                }
                if (srcAlpha <= 0f) {
                    idx += 4
                    continue
                }
                val ab = (dst[idx + 3].toInt() and 0xFF) / 255f
                val cbR = (dst[idx].toInt() and 0xFF) / 255f
                val cbG = (dst[idx + 1].toInt() and 0xFF) / 255f
                val cbB = (dst[idx + 2].toInt() and 0xFF) / 255f
                val csR = (src[idx].toInt() and 0xFF) / 255f
                val csG = (src[idx + 1].toInt() and 0xFF) / 255f
                val csB = (src[idx + 2].toInt() and 0xFF) / 255f

                blendPixel(cbR, cbG, cbB, csR, csG, csB, blendMode)
                val ao = srcAlpha + ab * (1f - srcAlpha)
                val inv = 1f / max(ao, 1e-6f)
                val coR = (srcAlpha * (1f - ab) * csR + srcAlpha * ab * blended[0] +
                    (1f - srcAlpha) * ab * cbR) * inv
                val coG = (srcAlpha * (1f - ab) * csG + srcAlpha * ab * blended[1] +
                    (1f - srcAlpha) * ab * cbG) * inv
                val coB = (srcAlpha * (1f - ab) * csB + srcAlpha * ab * blended[2] +
                    (1f - srcAlpha) * ab * cbB) * inv

                dst[idx] = quantize(coR)
                dst[idx + 1] = quantize(coG)
                dst[idx + 2] = quantize(coB)
                dst[idx + 3] = ((ao * 255f + 0.5f).toInt()).coerceIn(0, 255).toByte()
                idx += 4
            }
            composite.writeRow(y, dst)
        }
    }

    private fun quantize(value: Float): Byte =
        ((value * 255f + 0.5f).toInt()).coerceIn(0, 255).toByte()

    private fun blendPixel(
        cbR: Float, cbG: Float, cbB: Float,
        csR: Float, csG: Float, csB: Float,
        mode: Int,
    ) {
        when (mode) {
            10 -> { // COLOR: source H/S, backdrop L
                rgbToHsl(csR, csG, csB, hsl)
                rgbToHsl(cbR, cbG, cbB, hsl2)
                hslToRgb(hsl[0], hsl[1], hsl2[2], blended)
            }
            11 -> { // LUMINOSITY: backdrop H/S, source L
                rgbToHsl(csR, csG, csB, hsl)
                rgbToHsl(cbR, cbG, cbB, hsl2)
                hslToRgb(hsl2[0], hsl2[1], hsl[2], blended)
            }
            12 -> { // SATURATION
                rgbToHsl(csR, csG, csB, hsl)
                rgbToHsl(cbR, cbG, cbB, hsl2)
                hslToRgb(hsl2[0], hsl[1], hsl2[2], blended)
            }
            15 -> { // DARKER_COLOR
                if (cbR + cbG + cbB <= csR + csG + csB) {
                    blended[0] = cbR; blended[1] = cbG; blended[2] = cbB
                } else {
                    blended[0] = csR; blended[1] = csG; blended[2] = csB
                }
            }
            17 -> { // LIGHTER_COLOR
                if (cbR + cbG + cbB >= csR + csG + csB) {
                    blended[0] = cbR; blended[1] = cbG; blended[2] = cbB
                } else {
                    blended[0] = csR; blended[1] = csG; blended[2] = csB
                }
            }
            26 -> { // HUE
                rgbToHsl(csR, csG, csB, hsl)
                rgbToHsl(cbR, cbG, cbB, hsl2)
                hslToRgb(hsl[0], hsl2[1], hsl2[2], blended)
            }
            13, 27, 28, 29 -> {
                blended[0] = csR; blended[1] = csG; blended[2] = csB
            }
            else -> {
                blended[0] = blendChannel(cbR, csR, mode)
                blended[1] = blendChannel(cbG, csG, mode)
                blended[2] = blendChannel(cbB, csB, mode)
            }
        }
    }

    private fun blendChannel(cb: Float, cs: Float, mode: Int): Float = when (mode) {
        0 -> cs
        1 -> cb * cs
        2 -> 1f - (1f - cb) * (1f - cs)
        3 -> min(1f, cb + cs)
        4 -> min(cb, cs)
        5 -> if (cs <= 0f) 0f else 1f - min(1f, (1f - cb) / cs)
        6 -> if (cs >= 1f) 1f else min(1f, cb / (1f - cs))
        7 -> if (cb <= 0.5f) 2f * cb * cs else 1f - 2f * (1f - cb) * (1f - cs)
        8 -> {
            val d = if (cb <= 0.25f) ((16f * cb - 12f) * cb + 4f) * cb
            else sqrt(max(cb, 0f))
            if (cs <= 0.5f) cb - (1f - 2f * cs) * cb * (1f - cb)
            else cb + (2f * cs - 1f) * (d - cb)
        }
        9 -> if (cs <= 0f) 1f else min(1f, cb / cs)
        14 -> max(0f, cb + cs - 1f)
        16 -> max(cb, cs)
        18 -> if (cs <= 0.5f) 2f * cb * cs else 1f - 2f * (1f - cb) * (1f - cs)
        19 -> if (cs <= 0.5f) {
            if (cb <= 0f) 0f else 1f - min(1f, (1f - cb) / max(2f * cs, 1e-6f))
        } else {
            if (cb >= 1f) 1f else min(1f, cb / max(2f * (1f - cs), 1e-6f))
        }
        20 -> (cb + 2f * cs - 1f).coerceIn(0f, 1f)
        21 -> if (cs <= 0.5f) min(cb, 2f * cs) else max(cb, 2f * cs - 1f)
        22 -> if (cb + cs >= 1f) 1f else 0f
        23 -> abs(cb - cs)
        24 -> cb + cs - 2f * cb * cs
        25 -> max(0f, cb - cs)
        else -> cs
    }

    private fun rgbToHsl(r: Float, g: Float, b: Float, out: FloatArray) {
        val mx = max(r, max(g, b))
        val mn = min(r, min(g, b))
        val l = (mx + mn) * 0.5f
        val d = mx - mn
        val s = if (d == 0f) 0f else d / max(1e-12f, if (l < 0.5f) mx + mn else 2f - mx - mn)
        var h = 0f
        if (d > 0f) {
            val rc = (mx - r) / d
            val gc = (mx - g) / d
            val bc = (mx - b) / d
            h = when (mx) {
                r -> bc - gc
                g -> 2f + rc - bc
                else -> 4f + gc - rc
            }
            h = (h / 6f) % 1f
            if (h < 0f) h += 1f
        }
        out[0] = h
        out[1] = s
        out[2] = l
    }

    private fun hslToRgb(h: Float, s: Float, l: Float, out: FloatArray) {
        val q = if (l < 0.5f) l * (1f + s) else l + s - l * s
        val p = 2f * l - q
        out[0] = hue2rgb(p, q, h + 1f / 3f)
        out[1] = hue2rgb(p, q, h)
        out[2] = hue2rgb(p, q, h - 1f / 3f)
    }

    private fun hue2rgb(p: Float, q: Float, t0: Float): Float {
        var t = t0 % 1f
        if (t < 0f) t += 1f
        val res = when {
            t < 1f / 6f -> p + (q - p) * 6f * t
            t < 0.5f -> q
            t < 2f / 3f -> p + (q - p) * (2f / 3f - t) * 6f
            else -> p
        }
        return res.coerceIn(0f, 1f)
    }
}
