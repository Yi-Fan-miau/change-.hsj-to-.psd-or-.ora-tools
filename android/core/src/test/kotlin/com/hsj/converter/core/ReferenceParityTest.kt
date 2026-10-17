package com.hsj.converter.core

import org.json.JSONArray
import org.json.JSONObject
import org.junit.jupiter.api.Test
import java.io.File
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class ReferenceParityTest {
    private val samplesDir = File(System.getProperty("hsj.samplesDir") ?: "samples")
    private val referenceDir = File(System.getProperty("hsj.referenceDir") ?: "build/reference")
    private val workRoot = File(referenceDir.parentFile, "test-work")
    private val zstd = jvmZstd()

    @Test
    fun metadataAndLayerPixelsMatchPythonReference() {
        val refs = referenceDir.listFiles { f -> f.extension == "json" }?.sortedBy { it.name }
            ?: emptyList()
        assertTrue(refs.isNotEmpty(), "缺少参考 JSON：${referenceDir.absolutePath}")
        for (refFile in refs) {
            val json = JSONObject(refFile.readText(Charsets.UTF_8))
            val sampleName = json.getString("sample")
            val sample = File(samplesDir, sampleName)
            assertTrue(sample.isFile, "缺少样本：$sample")
            val work = File(workRoot, sample.nameWithoutExtension).apply { mkdirs() }
            val info = DraftInspector.inspect(sample, work)

            assertEquals(json.getInt("canvasWidth"), info.canvasWidth, "$sampleName width")
            assertEquals(json.getInt("canvasHeight"), info.canvasHeight, "$sampleName height")
            assertEquals(json.getInt("ppi"), info.ppi, "$sampleName ppi")
            assertEquals(json.getString("colorSpace"), info.colorSpace, "$sampleName colorSpace")
            assertEquals(json.getInt("bgArgb"), info.bgArgb, "$sampleName bgArgb")
            assertEquals(json.getBoolean("bgHidden"), info.bgHidden, "$sampleName bgHidden")
            assertEquals(json.getString("folderName"), info.folderName, "$sampleName folderName")
            if (json.isNull("paintName")) {
                assertEquals(null, info.paintName, "$sampleName paintName")
            } else {
                assertEquals(json.getString("paintName"), info.paintName, "$sampleName paintName")
            }

            assertTree(json.getJSONArray("tree"), info.roots, "$sampleName tree")

            val leavesJson = json.getJSONArray("leaves")
            val flat = LayerTree.flattenForPsd(info.roots)
            assertEquals(leavesJson.length(), flat.size, "$sampleName leaf count")
            for (i in 0 until leavesJson.length()) {
                val expected = leavesJson.getJSONObject(i)
                val actual = flat[i]
                val label = "$sampleName leaf ${expected.optString("flatName", i.toString())}"
                assertEquals(expected.getString("id"), actual.layer.id, "$label id")
                assertEquals(expected.getString("name"), actual.layer.name, "$label name")
                assertEquals(expected.getString("flatName"), actual.name, "$label flatName")
                assertEquals(expected.getDouble("opacity"), actual.layer.opacity.toDouble(), 1e-6, "$label opacity")
                assertEquals(expected.getDouble("effectiveOpacity"), actual.opacity.toDouble(), 1e-6, "$label effOpacity")
                assertEquals(expected.getBoolean("visible"), actual.layer.visible, "$label visible")
                assertEquals(expected.getBoolean("effectiveVisible"), actual.visible, "$label effVisible")
                assertEquals(expected.getInt("blendMode"), actual.layer.blendMode, "$label blendMode")
                assertEquals(expected.getInt("clipType"), actual.layer.clipType, "$label clipType")
                assertEquals(expected.getInt("clipGroup"), actual.layer.clipGroup, "$label clipGroup")
                assertEquals(expected.getBoolean("isLock"), actual.layer.isLock, "$label isLock")
                assertEquals(expected.getBoolean("isLockAlpha"), actual.layer.isLockAlpha, "$label isLockAlpha")
            }

            HsjArchive.open(sample, work).use { archive ->
                val surface = MappedRgbaSurface(
                    File(work, "test_layer.rgba"), info.canvasWidth, info.canvasHeight)
                surface.use {
                    val decoder = LayerDecoder(zstd)
                    for (i in 0 until leavesJson.length()) {
                        val expected = leavesJson.getJSONObject(i)
                        val leaf = flat[i].layer
                        val range = archive.layerRange(leaf.id)
                        if (range != null) {
                            decoder.decode(archive, range, info.canvasWidth, info.canvasHeight,
                                surface, NoopEngineListener)
                        } else {
                            surface.clear()
                        }
                        assertEquals(
                            expected.getString("pixelsSha256"),
                            surface.sha256(),
                            "$sampleName pixel hash for ${leaf.name} (${leaf.id})",
                        )
                    }
                }
            }
            println("reference parity OK: $sampleName (${flat.size} layers)")
        }
    }

    private fun assertTree(expected: JSONArray, actual: List<LayerInfo>, label: String) {
        assertEquals(expected.length(), actual.size, "$label child count")
        for (i in 0 until expected.length()) {
            val e = expected.getJSONObject(i)
            val a = actual[i]
            val name = "$label/${e.optString("name", i.toString())}"
            assertEquals(e.getString("id"), a.id, "$name id")
            assertEquals(e.getString("name"), a.name, "$name name")
            assertEquals(e.getDouble("opacity"), a.opacity.toDouble(), 1e-6, "$name opacity")
            assertEquals(e.getBoolean("visible"), a.visible, "$name visible")
            assertEquals(e.getInt("blendMode"), a.blendMode, "$name blendMode")
            assertEquals(e.getInt("clipType"), a.clipType, "$name clipType")
            assertEquals(e.getInt("clipGroup"), a.clipGroup, "$name clipGroup")
            assertEquals(e.getInt("layerNo"), a.layerNo, "$name layerNo")
            assertEquals(e.getBoolean("isGroup"), a.isGroup, "$name isGroup")
            assertEquals(e.getBoolean("isLock"), a.isLock, "$name isLock")
            assertEquals(e.getBoolean("isLockAlpha"), a.isLockAlpha, "$name isLockAlpha")
            assertTree(e.getJSONArray("children"), a.children, name)
        }
    }
}
