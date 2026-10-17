package com.hsj.converter.core

import net.jpountz.lz4.LZ4Factory

data class LayerDecodeResult(
    val bounds: RgbaRect?,
    val stripCount: Int,
    val layerWidth: Int,
    val layerHeight: Int,
    val version: Int,
)

/**
 * Decodes one layer file strip-by-strip into a full-canvas RGBA surface.
 * Never materializes a full layer as a Kotlin array.
 */
class LayerDecoder(
    private val zstd: ZstdBlockDecoder,
) {
    private val lz4 = LZ4Factory.safeInstance().safeDecompressor()

    fun decode(
        archive: HsjArchive,
        range: FileRange?,
        canvasWidth: Int,
        canvasHeight: Int,
        surface: MappedRgbaSurface,
        listener: EngineListener,
    ): LayerDecodeResult {
        require(surface.width == canvasWidth && surface.height == canvasHeight)
        surface.clear()
        if (range == null || range.length < 100) {
            return LayerDecodeResult(null, 0, canvasWidth, canvasHeight, 0)
        }

        val header = archive.readRange(range, 0, 100)
        if (header[0] != 'h'.code.toByte() || header[1] != 's'.code.toByte() ||
            header[2] != 'j'.code.toByte() || header[3] != 0.toByte()
        ) {
            throw HsjException("图层文件头不正确")
        }
        val version = ((header[4].toInt() and 0xFF) shl 16) or
            ((header[5].toInt() and 0xFF) shl 8) or
            (header[6].toInt() and 0xFF)
        if (version != 1 && version != 2) {
            throw HsjException("不支持的图层压缩版本: $version")
        }
        val layerWidth = beInt(header, 7)
        val layerHeight = beInt(header, 11)
        if (layerWidth <= 0 || layerHeight <= 0 || layerWidth > 100000 || layerHeight > 100000) {
            throw HsjException("图层尺寸无效: ${layerWidth}x$layerHeight")
        }

        var position = 100L
        var strips = 0
        var minX = canvasWidth
        var minY = canvasHeight
        var maxX = -1
        var maxY = -1

        while (position + 24 <= range.length) {
            if (listener.isCancelled()) throw ConversionCancelledException()
            val stripHeader = archive.readRange(range, position, 24)
            val usize = beInt(stripHeader, 0).toLong() and 0xFFFFFFFFL
            val csize = beInt(stripHeader, 4).toLong() and 0xFFFFFFFFL
            val x = beInt(stripHeader, 8)
            val y = beInt(stripHeader, 12)
            val h = beInt(stripHeader, 20)
            if (usize == 0L || csize == 0L) break
            if (x < 0 || y < 0) {
                position += 24 + csize
                continue
            }
            if (usize > 512L * 1024 * 1024 || csize > 512L * 1024 * 1024) {
                throw HsjException("图层分条过大")
            }
            if (position + 24 + csize > range.length) break
            if (h <= 0) throw HsjException("图层分条高度无效")

            val compressed = archive.readRange(range, position + 24, csize.toInt())
            val raw = when (version) {
                1 -> {
                    val dst = ByteArray(usize.toInt())
                    val written = lz4.decompress(compressed, 0, compressed.size, dst, 0, dst.size)
                    if (written != dst.size) throw HsjException("LZ4 解压长度不匹配")
                    dst
                }
                else -> {
                    val dst = zstd.decompress(compressed, 0, compressed.size, usize.toInt())
                    if (dst.size != usize.toInt()) throw HsjException("Zstd 解压长度不匹配")
                    dst
                }
            }
            if (raw.size % (h * 4) != 0) throw HsjException("图层分条数据长度无效")
            val sw = raw.size / (h * 4)
            if (sw <= 0) throw HsjException("图层分条宽度无效")

            val top = canvasHeight - (y + h)
            val copyW = minOf(sw, canvasWidth - x, layerWidth - x)
            if (copyW > 0) {
                for (row in 0 until h) {
                    val dstY = top + row
                    if (dstY < 0 || dstY >= canvasHeight) continue
                    val srcRow = h - 1 - row
                    val srcOff = srcRow * sw * 4
                    surface.putRow(x, dstY, raw, srcOff, copyW * 4)
                    var i = srcOff + 3
                    val end = srcOff + copyW * 4
                    var px = x
                    while (i < end) {
                        if (raw[i].toInt() != 0) {
                            if (px < minX) minX = px
                            if (px > maxX) maxX = px
                            if (dstY < minY) minY = dstY
                            if (dstY > maxY) maxY = dstY
                        }
                        px++
                        i += 4
                    }
                }
            }
            strips++
            position += 24 + csize
        }

        val bounds = if (maxX >= 0) RgbaRect(minX, minY, maxX + 1, maxY + 1) else null
        return LayerDecodeResult(bounds, strips, layerWidth, layerHeight, version)
    }
}
