package com.hsj.converter.core

import org.junit.jupiter.api.Test
import java.io.File
import kotlin.test.assertTrue

class ConversionSmokeTest {
    private val samplesDir = File(System.getProperty("hsj.samplesDir") ?: "samples")
    private val referenceDir = File(System.getProperty("hsj.referenceDir") ?: "build/reference")

    @Test
    fun test47BothFormats() {
        convert("test47.hsj", 100_000, 10_000)
    }

    @Test
    fun image6000BothFormats() {
        convert("图像.hsj", 1_000_000, 100_000)
    }

    private fun convert(name: String, minPsd: Long, minOra: Long) {
        val runDir = File(referenceDir.parentFile, "android-output/run-${System.nanoTime()}")
            .apply { mkdirs() }
        val work = File(runDir, "work").apply { mkdirs() }
        val psd = File(runDir, name.substringBeforeLast('.') + ".psd")
        val ora = File(runDir, name.substringBeforeLast('.') + ".ora")
        val t0 = System.nanoTime()
        val result = ConversionEngine(jvmZstd()).convert(
            File(samplesDir, name),
            ConvertRequest(Format.BOTH, includeBackground = true,
                psdFile = psd, oraFile = ora, workDir = work),
        )
        assertTrue(psd.isFile && psd.length() > minPsd, "PSD output missing")
        assertTrue(ora.isFile && ora.length() > minOra, "ORA output missing")
        println("SMOKE_OUTPUT=$runDir")
        println("$name PSD=${psd.length()} ORA=${ora.length()} warnings=${result.warnings.size} " +
            "time=${(System.nanoTime() - t0) / 1_000_000}ms")
    }
}
