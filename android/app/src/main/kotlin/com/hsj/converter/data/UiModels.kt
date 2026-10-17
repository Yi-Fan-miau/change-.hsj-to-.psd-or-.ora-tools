package com.hsj.converter.data

import android.net.Uri
import com.hsj.converter.core.DraftInfo
import com.hsj.converter.core.Format
import com.hsj.converter.core.LayerInfo
import com.hsj.converter.core.LogLevel
import com.hsj.converter.core.Stage
import java.io.File

data class LogEntry(
    val timestamp: Long,
    val level: LogLevel,
    val message: String,
)

data class SavedOutput(
    val name: String,
    val uri: Uri,
    val format: Format,
)

data class JobState(
    val running: Boolean = false,
    val stage: Stage? = null,
    val done: Int = 0,
    val total: Int = 0,
    val fraction: Float = 0f,
    val message: String = "",
    val logs: List<LogEntry> = emptyList(),
    val result: List<SavedOutput> = emptyList(),
    val warnings: List<String> = emptyList(),
    val error: String? = null,
    val cancelled: Boolean = false,
    val durationMs: Long = 0,
)

data class UiState(
    val inputName: String? = null,
    val inputFile: File? = null,
    val draft: DraftInfo? = null,
    val loading: Boolean = false,
    val includeBackground: Boolean = true,
    val format: Format = Format.PSD,
    val outputTreeUri: Uri? = null,
    val outputFolderName: String? = null,
    val outputName: String = "",
    val overwrite: Boolean = false,
    val expandedGroups: Set<String> = emptySet(),
    val pendingOverwrite: List<String> = emptyList(),
    val showAbout: Boolean = false,
    val showLog: Boolean = false,
    val message: String? = null,
) {
    val outputNames: List<String>
        get() {
            val base = sanitizeOutputName(outputName).ifBlank { "draft" }
            return when (format) {
                Format.PSD -> listOf("$base.psd")
                Format.ORA -> listOf("$base.ora")
                Format.BOTH -> listOf("$base.psd", "$base.ora")
            }
        }

    fun displayRoots(): List<LayerInfo> {
        val info = draft ?: return emptyList()
        if (!info.includeBackground(includeBackground)) return info.roots
        val bg = LayerInfo(
            id = "__background__",
            name = "背景",
            opacity = 1f,
            visible = true,
            blendMode = 0,
            clipType = 0,
            clipGroup = 0,
            isGroup = false,
            isLock = false,
            isLockAlpha = false,
        )
        return listOf(bg) + info.roots
    }
}

data class LayerRow(
    val layer: LayerInfo,
    val depth: Int,
    val hasChildren: Boolean,
    val expanded: Boolean,
)

fun sanitizeOutputName(raw: String): String {
    var name = raw.trim()
    if (name.lowercase().endsWith(".psd") || name.lowercase().endsWith(".ora")) {
        name = name.substringBeforeLast('.')
    }
    name = name.replace(Regex("[<>:\"/\\\\|?*\\u0000-\\u001F]"), "_")
    return name.trim(' ', '.')
}

fun formatMime(format: Format): String = when (format) {
    Format.PSD -> "image/vnd.adobe.photoshop"
    Format.ORA -> "image/openraster"
    Format.BOTH -> "application/octet-stream"
}

fun extension(format: Format): String = when (format) {
    Format.PSD -> "psd"
    Format.ORA -> "ora"
    Format.BOTH -> ""
}

fun flattenLayerRows(roots: List<LayerInfo>, expanded: Set<String>): List<LayerRow> {
    val out = ArrayList<LayerRow>()
    fun walk(items: List<LayerInfo>, depth: Int) {
        for (item in items.asReversed()) {
            val hasChildren = item.children.isNotEmpty()
            val isExpanded = !hasChildren || expanded.contains(displayKey(item))
            out += LayerRow(item, depth, hasChildren, isExpanded)
            if (hasChildren && isExpanded) {
                walk(item.children, depth + 1)
            }
        }
    }
    walk(roots, 0)
    return out
}

fun displayKey(layer: LayerInfo): String =
    layer.id.ifBlank { "${layer.name}:${System.identityHashCode(layer)}" }

fun allGroupKeys(roots: List<LayerInfo>): Set<String> {
    val out = HashSet<String>()
    fun walk(items: List<LayerInfo>) {
        for (item in items) {
            if (item.children.isNotEmpty()) {
                out += displayKey(item)
                walk(item.children)
            }
        }
    }
    walk(roots)
    return out
}

fun clipLabel(layer: LayerInfo): String = when (layer.clipType) {
    3 -> if (layer.clipGroup != 0) "基础组${layer.clipGroup}" else ""
    1, 2 -> if (layer.clipGroup != 0) "剪贴组${layer.clipGroup}" else ""
    else -> ""
}

fun layerType(layer: LayerInfo): String {
    var type = if (layer.isGroup) "组" else "图层"
    if (layer.isLockAlpha) type += " · 锁"
    return type
}
