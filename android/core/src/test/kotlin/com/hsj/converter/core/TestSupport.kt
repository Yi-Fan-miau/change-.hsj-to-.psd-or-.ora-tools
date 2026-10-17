package com.hsj.converter.core

internal fun jvmZstd(): ZstdBlockDecoder = object : ZstdBlockDecoder {
    override fun decompress(
        src: ByteArray,
        srcOffset: Int,
        srcLength: Int,
        dstSize: Int,
    ): ByteArray {
        val input = src.copyOfRange(srcOffset, srcOffset + srcLength)
        return com.github.luben.zstd.Zstd.decompress(input, dstSize)
    }
}
