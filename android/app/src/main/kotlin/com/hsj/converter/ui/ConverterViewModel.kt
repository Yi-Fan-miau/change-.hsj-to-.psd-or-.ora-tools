package com.hsj.converter.ui

import android.app.Application
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.util.Log
import androidx.core.content.ContextCompat
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.hsj.converter.core.DraftInfo
import com.hsj.converter.core.DraftInspector
import com.hsj.converter.core.Format
import com.hsj.converter.core.LogLevel
import com.hsj.converter.data.JobRepository
import com.hsj.converter.data.JobState
import com.hsj.converter.data.SavedOutput
import com.hsj.converter.data.SafFiles
import com.hsj.converter.data.UiState
import com.hsj.converter.data.allGroupKeys
import com.hsj.converter.data.formatMime
import com.hsj.converter.data.sanitizeOutputName
import com.hsj.converter.service.ConversionService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class ConverterViewModel(application: Application) : AndroidViewModel(application) {
    private val tag = "HSJConverter"
    private val prefs = application.getSharedPreferences("hsj_prefs", Context.MODE_PRIVATE)
    private val _ui = MutableStateFlow(UiState())
    val ui: StateFlow<UiState> = _ui.asStateFlow()
    val job: StateFlow<JobState> = JobRepository.state
    private var importJob: Job? = null

    init {
        val tree = prefs.getString("output_tree", null)
        if (tree != null) {
            val uri = Uri.parse(tree)
            SafFiles.takePersistablePermission(application, uri)
            _ui.value = _ui.value.copy(
                outputTreeUri = uri,
                outputFolderName = SafFiles.folderName(application, uri),
            )
        }
    }

    fun importUri(uri: Uri) {
        if (JobRepository.state.value.running) {
            _ui.value = _ui.value.copy(message = "转换正在进行，请稍后再导入新草稿")
            return
        }
        importJob?.cancel()
        importJob = viewModelScope.launch {
            _ui.value = _ui.value.copy(loading = true, message = null)
            JobRepository.reset()
            JobRepository.log(LogLevel.INFO, "正在读取草稿…")
            try {
                val result = withContext(Dispatchers.IO) {
                    val app = getApplication<Application>()
                    val input = SafFiles.copyToCache(
                        app, uri, File(app.cacheDir, "imports"))
                    val inspectDir = File(app.cacheDir, "inspect/${System.currentTimeMillis()}")
                    try {
                        val info = DraftInspector.inspect(input, inspectDir)
                        Triple(input, info, SafFiles.displayName(app, uri))
                    } finally {
                        inspectDir.deleteRecursively()
                    }
                }
                val (file, info, displayName) = result
                val stem = (displayName ?: file.name)
                    .substringBeforeLast('.', (displayName ?: file.name))
                    .ifBlank { "draft" }
                val expanded = allGroupKeys(info.roots)
                _ui.value = _ui.value.copy(
                    inputName = displayName ?: file.name,
                    inputFile = file,
                    draft = info,
                    loading = false,
                    outputName = sanitizeOutputName(stem),
                    expandedGroups = expanded,
                    includeBackground = true,
                    pendingOverwrite = emptyList(),
                )
                Log.i(tag, "import ok ${displayName ?: file.name} ${info.canvasWidth}x${info.canvasHeight} layers=${info.layerCount}")
                JobRepository.log(
                    LogLevel.SUCCESS,
                    "已读取 ${displayName ?: file.name}：${info.canvasWidth}×${info.canvasHeight}，" +
                        "${info.layerCount} 个图层",
                )
                info.warnings.forEach { JobRepository.log(LogLevel.WARN, it) }
            } catch (t: Throwable) {
                Log.e(tag, "import failed", t)
                _ui.value = _ui.value.copy(loading = false, message = t.message ?: "读取失败")
                JobRepository.log(LogLevel.ERROR, "读取失败：${t.message}")
            }
        }
    }

    fun setOutputTree(uri: Uri) {
        val app = getApplication<Application>()
        SafFiles.takePersistablePermission(app, uri)
        prefs.edit().putString("output_tree", uri.toString()).apply()
        _ui.value = _ui.value.copy(
            outputTreeUri = uri,
            outputFolderName = SafFiles.folderName(app, uri),
            pendingOverwrite = emptyList(),
        )
    }

    fun setFormat(format: Format) {
        _ui.value = _ui.value.copy(format = format)
    }

    fun setIncludeBackground(value: Boolean) {
        _ui.value = _ui.value.copy(includeBackground = value)
    }

    fun setOverwrite(value: Boolean) {
        _ui.value = _ui.value.copy(overwrite = value)
    }

    fun setOutputName(name: String) {
        _ui.value = _ui.value.copy(outputName = name)
    }

    fun toggleGroup(key: String) {
        val current = _ui.value.expandedGroups
        _ui.value = _ui.value.copy(
            expandedGroups = if (key in current) current - key else current + key)
    }

    fun startConversion(forceOverwrite: Boolean = false) {
        val state = _ui.value
        if (JobRepository.state.value.running) {
            _ui.value = state.copy(message = "转换正在进行")
            return
        }
        val draft: DraftInfo = state.draft
            ?: run { _ui.value = state.copy(message = "请先选择 .hsj 文件"); return }
        val tree = state.outputTreeUri
            ?: run { _ui.value = state.copy(message = "请选择输出文件夹"); return }
        val base = sanitizeOutputName(state.outputName)
            .ifBlank { draft.input.nameWithoutExtension }
        val names = when (state.format) {
            Format.PSD -> listOf("$base.psd")
            Format.ORA -> listOf("$base.ora")
            Format.BOTH -> listOf("$base.psd", "$base.ora")
        }
        val overwrite = forceOverwrite || state.overwrite
        viewModelScope.launch {
            val existing = withContext(Dispatchers.IO) {
                runCatching { SafFiles.existingNames(getApplication(), tree, names) }
                    .getOrDefault(emptyList())
            }
            if (!overwrite && existing.isNotEmpty()) {
                _ui.value = _ui.value.copy(pendingOverwrite = existing)
                return@launch
            }
            Log.i(tag, "start conversion input=${draft.input.absolutePath} format=${state.format} bg=${state.includeBackground} overwrite=$overwrite names=$names")
            val app = getApplication<Application>()
            val intent = Intent(app, ConversionService::class.java).apply {
                action = ConversionService.ACTION_START
                putExtra(ConversionService.EXTRA_INPUT, draft.input.absolutePath)
                putExtra(ConversionService.EXTRA_TREE, tree.toString())
                putExtra(ConversionService.EXTRA_BASE_NAME, base)
                putExtra(ConversionService.EXTRA_FORMAT, state.format.name)
                putExtra(ConversionService.EXTRA_INCLUDE_BG, state.includeBackground)
                putExtra(ConversionService.EXTRA_OVERWRITE, overwrite)
            }
            try {
                ContextCompat.startForegroundService(app, intent)
                _ui.value = _ui.value.copy(
                    pendingOverwrite = emptyList(), message = "转换任务已开始")
            } catch (t: Throwable) {
                _ui.value = _ui.value.copy(message = "无法启动转换：${t.message}")
                JobRepository.fail(t.message ?: "无法启动转换")
            }
        }
    }

    fun confirmOverwrite() {
        _ui.value = _ui.value.copy(overwrite = true, pendingOverwrite = emptyList())
        startConversion(forceOverwrite = true)
    }

    fun dismissOverwrite() {
        _ui.value = _ui.value.copy(pendingOverwrite = emptyList())
    }

    fun cancelJob() {
        val app = getApplication<Application>()
        val intent = Intent(app, ConversionService::class.java)
            .setAction(ConversionService.ACTION_CANCEL)
        app.startService(intent)
    }

    fun openOutput(output: SavedOutput) {
        val app = getApplication<Application>()
        val mime = formatMime(output.format)
        val view = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(output.uri, mime)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        try {
            app.startActivity(view)
        } catch (_: Exception) {
            shareOutput(output)
        }
    }

    fun shareOutput(output: SavedOutput) {
        val app = getApplication<Application>()
        val send = Intent(Intent.ACTION_SEND).apply {
            type = formatMime(output.format)
            putExtra(Intent.EXTRA_STREAM, output.uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        app.startActivity(
            Intent.createChooser(send, "分享 ${output.name}")
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    fun copyLogs() {
        val app = getApplication<Application>()
        val text = job.value.logs.joinToString("\n") { entry ->
            val time = SimpleDateFormat("HH:mm:ss", Locale.CHINA).format(Date(entry.timestamp))
            "[$time] ${entry.message}"
        }
        val clip = app.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        clip.setPrimaryClip(ClipData.newPlainText("HSJ 日志", text))
        _ui.value = _ui.value.copy(message = "日志已复制")
    }

    fun clearLogs() {
        JobRepository.clearLogs()
    }

    fun showLog(value: Boolean) {
        _ui.value = _ui.value.copy(showLog = value)
    }

    fun showAbout(value: Boolean) {
        _ui.value = _ui.value.copy(showAbout = value)
    }

    fun clearMessage() {
        _ui.value = _ui.value.copy(message = null)
    }
}
