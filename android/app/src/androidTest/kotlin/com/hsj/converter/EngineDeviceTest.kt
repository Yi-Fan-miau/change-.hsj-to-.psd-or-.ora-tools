package com.hsj.converter

import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.hsj.converter.codec.ZstdJniBlockDecoder
import com.hsj.converter.core.ConversionEngine
import com.hsj.converter.core.ConvertRequest
import com.hsj.converter.core.Format
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class EngineDeviceTest {
    @Test
    fun test47OnDevice() {
        run("test47.hsj", 100_000, 10_000)
    }

    @Test
    fun image6000OnDevice() {
        run("image6000.hsj", 1_000_000, 100_000)
    }

    private fun run(name: String, minPsd: Long, minOra: Long) {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val base = context.getExternalFilesDir(null) ?: context.filesDir
        val input = File(base, name)
        assumeTrue("push $name to ${base.absolutePath}", input.isFile)
        val run = File(base, "out-${System.nanoTime()}").apply { mkdirs() }
        val work = File(run, "work").apply { mkdirs() }
        val psd = File(run, name.substringBeforeLast('.') + ".psd")
        val ora = File(run, name.substringBeforeLast('.') + ".ora")
        val t0 = System.nanoTime()
        val result = ConversionEngine(ZstdJniBlockDecoder()).convert(
            input,
            ConvertRequest(Format.BOTH, true, psd, ora, work),
        )
        assertTrue("PSD missing", psd.isFile && psd.length() > minPsd)
        assertTrue("ORA missing", ora.isFile && ora.length() > minOra)
        println("DEVICE_OUTPUT=${run.absolutePath}")
        println("$name PSD=${psd.length()} ORA=${ora.length()} " +
            "warnings=${result.warnings.size} time=${(System.nanoTime() - t0) / 1_000_000}ms")
    }
}
