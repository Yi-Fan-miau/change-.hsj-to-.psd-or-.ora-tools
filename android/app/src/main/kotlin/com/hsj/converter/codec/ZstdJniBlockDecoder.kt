package com.hsj.converter.codec

import com.github.luben.zstd.Zstd
import com.hsj.converter.core.ZstdBlockDecoder

class ZstdJniBlockDecoder : ZstdBlockDecoder {
    override fun decompress(
        src: ByteArray,
        srcOffset: Int,
        srcLength: Int,
        dstSize: Int,
    ): ByteArray {
        val input = if (srcOffset == 0 && srcLength == src.size) {
            src
        } else {
            src.copyOfRange(srcOffset, srcOffset + srcLength)
        }
        val out = Zstd.decompress(input, dstSize)
        if (out.size != dstSize) {
            throw IllegalStateException("Zstd 解压长度不匹配：${out.size} != $dstSize")
        }
        return out
    }
}
