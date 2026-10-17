package com.hsj.converter.ui

import android.Manifest
import android.content.Intent
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.ContentCopy
import androidx.compose.material.icons.outlined.DeleteOutline
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material.icons.outlined.Folder
import androidx.compose.material.icons.outlined.FolderOpen
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.KeyboardArrowDown
import androidx.compose.material.icons.outlined.KeyboardArrowRight
import androidx.compose.material.icons.outlined.Layers
import androidx.compose.material.icons.outlined.OpenInNew
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material.icons.outlined.Visibility
import androidx.compose.material.icons.outlined.VisibilityOff
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.hsj.converter.R
import com.hsj.converter.core.Format
import com.hsj.converter.core.LayerInfo
import com.hsj.converter.core.LayerTree
import com.hsj.converter.core.LogLevel
import com.hsj.converter.core.Stage
import com.hsj.converter.data.JobState
import com.hsj.converter.data.LayerRow
import com.hsj.converter.data.LogEntry
import com.hsj.converter.data.SavedOutput
import com.hsj.converter.data.UiState
import com.hsj.converter.data.clipLabel
import com.hsj.converter.data.displayKey
import com.hsj.converter.data.flattenLayerRows
import com.hsj.converter.data.sanitizeOutputName
import com.hsj.converter.ui.theme.HsjColors
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.roundToInt

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ConverterScreen(vm: ConverterViewModel) {
    val ui by vm.ui.collectAsStateWithLifecycle()
    val job by vm.job.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    val openDoc = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri -> uri?.let(vm::importUri) }
    val openTree = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocumentTree()
    ) { uri -> uri?.let(vm::setOutputTree) }
    val notificationPermission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { }

    LaunchedEffect(Unit) {
        if (Build.VERSION.SDK_INT >= 33) {
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }
    LaunchedEffect(ui.message) {
        ui.message?.let {
            snackbar.showSnackbar(it)
            vm.clearMessage()
        }
    }

    BoxWithConstraints(
        Modifier
            .fillMaxSize()
            .background(HsjColors.Background)
            .statusBarsPadding()
            .navigationBarsPadding()
    ) {
        val wide = maxWidth >= 720.dp
        Column(Modifier.fillMaxSize()) {
            AppHeader(onAbout = { vm.showAbout(true) })
            if (wide) {
                Row(Modifier.fillMaxSize()) {
                    Column(
                        Modifier
                            .weight(0.42f)
                            .fillMaxHeight(),
                    ) {
                        LazyColumn(
                            Modifier
                                .weight(1f)
                                .fillMaxWidth(),
                            contentPadding = androidx.compose.foundation.layout.PaddingValues(
                                start = 16.dp, end = 16.dp, top = 16.dp, bottom = 8.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            item {
                                ImportCard(ui, job, onPick = { openDoc.launch(arrayOf("*/*")) })
                            }
                            item {
                                SettingsCard(
                                    ui = ui,
                                    job = job,
                                    onPickOutput = { openTree.launch(null) },
                                    onFormat = vm::setFormat,
                                    onBackground = vm::setIncludeBackground,
                                    onOverwrite = vm::setOverwrite,
                                    onName = vm::setOutputName,
                                )
                            }
                            item { ProgressCard(job, onCancel = vm::cancelJob) }
                            item {
                                ResultCard(
                                    job,
                                    onOpen = vm::openOutput,
                                    onShare = vm::shareOutput,
                                )
                            }
                        }
                        ConvertBar(ui, job, onConvert = { vm.startConversion() })
                    }
                    LazyColumn(
                        Modifier
                            .weight(0.58f)
                            .fillMaxHeight(),
                        contentPadding = androidx.compose.foundation.layout.PaddingValues(
                            start = 0.dp, end = 16.dp, top = 16.dp, bottom = 16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        item { LayerTreeCard(ui, onToggle = vm::toggleGroup) }
                        item {
                            LogCard(
                                job,
                                onShowAll = { vm.showLog(true) },
                                onCopy = vm::copyLogs,
                                onClear = vm::clearLogs,
                            )
                        }
                    }
                }
            } else {
                Column(
                    Modifier
                        .weight(1f)
                        .fillMaxWidth(),
                ) {
                    LazyColumn(
                        Modifier
                            .weight(1f)
                            .fillMaxWidth(),
                        contentPadding = androidx.compose.foundation.layout.PaddingValues(
                            start = 16.dp, end = 16.dp, top = 16.dp, bottom = 8.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        item {
                            ImportCard(ui, job, onPick = { openDoc.launch(arrayOf("*/*")) })
                        }
                        item {
                            SettingsCard(
                                ui = ui,
                                job = job,
                                onPickOutput = { openTree.launch(null) },
                                onFormat = vm::setFormat,
                                onBackground = vm::setIncludeBackground,
                                onOverwrite = vm::setOverwrite,
                                onName = vm::setOutputName,
                            )
                        }
                        item { ProgressCard(job, onCancel = vm::cancelJob) }
                        item {
                            ResultCard(job, onOpen = vm::openOutput, onShare = vm::shareOutput)
                        }
                        item { LayerTreeCard(ui, onToggle = vm::toggleGroup) }
                        item {
                            LogCard(
                                job,
                                onShowAll = { vm.showLog(true) },
                                onCopy = vm::copyLogs,
                                onClear = vm::clearLogs,
                            )
                        }
                    }
                    ConvertBar(ui, job, onConvert = { vm.startConversion() })
                }
            }
        }
        SnackbarHost(
            hostState = snackbar,
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(16.dp),
        )
    }

    if (ui.pendingOverwrite.isNotEmpty()) {
        AlertDialog(
            onDismissRequest = vm::dismissOverwrite,
            title = { Text("文件已存在") },
            text = {
                Text("以下文件已存在，是否覆盖？\n\n" + ui.pendingOverwrite.joinToString("\n"))
            },
            confirmButton = {
                TextButton(onClick = vm::confirmOverwrite) { Text("覆盖") }
            },
            dismissButton = {
                TextButton(onClick = vm::dismissOverwrite) { Text("取消") }
            },
        )
    }
    if (ui.showAbout) {
        AboutDialog(onDismiss = { vm.showAbout(false) })
    }
    if (ui.showLog) {
        LogSheet(
            logs = job.logs,
            onDismiss = { vm.showLog(false) },
            onCopy = vm::copyLogs,
            onClear = vm::clearLogs,
        )
    }
}

@Composable
private fun AppHeader(onAbout: () -> Unit) {
    Box(
        Modifier
            .fillMaxWidth()
            .height(104.dp)
            .background(
                Brush.linearGradient(
                    listOf(Color(0xFF100E1E), Color(0xFF251C4E), Color(0xFF143E4A))
                )
            )
    ) {
        Row(
            Modifier
                .fillMaxSize()
                .padding(horizontal = 20.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            androidx.compose.foundation.Image(
                painter = painterResource(R.drawable.app_icon),
                contentDescription = null,
                contentScale = ContentScale.Fit,
                modifier = Modifier
                    .size(58.dp)
                    .clip(RoundedCornerShape(16.dp)),
            )
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    "HSJ 转换器",
                    style = MaterialTheme.typography.headlineSmall,
                    color = HsjColors.Text,
                )
                Spacer(Modifier.height(3.dp))
                Text(
                    "画世界Pro 草稿 → PSD / ORA · 本地离线",
                    style = MaterialTheme.typography.bodySmall,
                    color = Color(0xFFB4BCD4),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Text(
                "v1.0.0",
                style = MaterialTheme.typography.labelSmall,
                color = Color(0xFFC9BEFF),
                modifier = Modifier
                    .clip(CircleShape)
                    .background(Color(0xFF201B3C))
                    .padding(horizontal = 9.dp, vertical = 5.dp),
            )
            IconButton(onClick = onAbout) {
                Icon(Icons.Outlined.Info, contentDescription = "关于", tint = Color(0xFFD7DDF0))
            }
        }
    }
}

@Composable
private fun SectionCard(
    title: String,
    subtitle: String? = null,
    action: (@Composable () -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = HsjColors.Surface),
        border = BorderStroke(1.dp, HsjColors.Border),
    ) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier
                        .width(3.dp)
                        .height(18.dp)
                        .background(HsjColors.Primary, RoundedCornerShape(2.dp))
                )
                Spacer(Modifier.width(9.dp))
                Column(Modifier.weight(1f)) {
                    Text(title, style = MaterialTheme.typography.titleMedium, color = HsjColors.Text)
                    if (subtitle != null) {
                        Text(
                            subtitle,
                            style = MaterialTheme.typography.labelSmall,
                            color = HsjColors.Hint,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
                action?.invoke()
            }
            Spacer(Modifier.height(12.dp))
            content()
        }
    }
}

@Composable
private fun ImportCard(ui: UiState, job: JobState, onPick: () -> Unit) {
    SectionCard(
        title = "草稿文件",
        subtitle = "画世界Pro 3.4.6 导出的 .hsj · 转换全程在本机完成",
        action = if (ui.draft != null) {
            {
                TextButton(onClick = onPick, enabled = !job.running) { Text("更换") }
            }
        } else null,
    ) {
        val draft = ui.draft
        when {
            ui.loading -> Row(verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(
                    Modifier.size(18.dp), strokeWidth = 2.dp, color = HsjColors.Cyan)
                Spacer(Modifier.width(10.dp))
                Text("正在读取图层信息…", style = MaterialTheme.typography.bodyMedium,
                    color = HsjColors.Muted)
            }
            draft == null -> {
                Text(
                    "选择 .hsj 文件后，这里会显示画布尺寸与图层信息。",
                    style = MaterialTheme.typography.bodySmall,
                    color = HsjColors.Hint,
                )
                Spacer(Modifier.height(12.dp))
                OutlinedButton(onClick = onPick) {
                    Icon(Icons.Outlined.FolderOpen, contentDescription = null,
                        modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(8.dp))
                    Text("选择 .hsj 草稿")
                }
            }
            else -> {
                Text(
                    ui.inputName ?: "草稿.hsj",
                    style = MaterialTheme.typography.titleMedium,
                    color = HsjColors.Text,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.height(5.dp))
                Text(
                    "画布 ${draft.canvasWidth} × ${draft.canvasHeight} px · ${draft.ppi} PPI · " +
                        "${draft.layerCount} 个图层",
                    style = MaterialTheme.typography.bodySmall,
                    color = HsjColors.Muted,
                )
                if (draft.colorSpace.isNotBlank()) {
                    Text(
                        "色彩空间 ${draft.colorSpace}（不嵌入 ICC）",
                        style = MaterialTheme.typography.labelSmall,
                        color = HsjColors.Hint,
                    )
                }
                Spacer(Modifier.height(8.dp))
                val rgba = draft.backgroundRgba()
                val bgText = when {
                    draft.bgHidden -> "背景隐藏"
                    !draft.includeBackground(true) -> "背景透明"
                    !ui.includeBackground -> "不含背景层"
                    else -> "背景 rgba(${rgba[0]},${rgba[1]},${rgba[2]},${rgba[3]})"
                }
                Row(
                    Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    Pill("${draft.layerCount} 层")
                    Pill(bgText, HsjColors.Cyan)
                    val hidden = draft.leaves.count { !it.layer.visible }
                    if (hidden > 0) Pill("$hidden 隐藏", HsjColors.Warning)
                    val clips = draft.leaves.count { it.layer.clipGroup != 0 }
                    if (clips > 0) Pill("$clips 剪贴", Color(0xFFC3B6FF))
                }
                if (draft.warnings.isNotEmpty()) {
                    Spacer(Modifier.height(8.dp))
                    Text(
                        draft.warnings.first(),
                        style = MaterialTheme.typography.labelSmall,
                        color = HsjColors.Warning,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SettingsCard(
    ui: UiState,
    job: JobState,
    onPickOutput: () -> Unit,
    onFormat: (Format) -> Unit,
    onBackground: (Boolean) -> Unit,
    onOverwrite: (Boolean) -> Unit,
    onName: (String) -> Unit,
) {
    val enabled = !job.running && !ui.loading
    val draft = ui.draft
    val tooLargeForPsd = draft != null && ui.format.includesPsd &&
        (draft.canvasWidth > 30000 || draft.canvasHeight > 30000)

    SectionCard(title = "转换设置", subtitle = "输出格式与保存选项") {
        Text("输出格式", style = MaterialTheme.typography.labelSmall, color = HsjColors.Muted)
        Spacer(Modifier.height(6.dp))
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            val options = listOf(
                Format.PSD to "PSD",
                Format.ORA to "ORA",
                Format.BOTH to "两者",
            )
            options.forEachIndexed { index, (format, label) ->
                SegmentedButton(
                    selected = ui.format == format,
                    onClick = { onFormat(format) },
                    enabled = enabled,
                    shape = SegmentedButtonDefaults.itemShape(index, options.size),
                    label = { Text(label) },
                    icon = {},
                )
            }
        }
        Spacer(Modifier.height(6.dp))
        Text(
            "PSD 兼容 Photoshop / Krita；ORA 兼容 Krita / GIMP",
            style = MaterialTheme.typography.labelSmall,
            color = HsjColors.Hint,
        )

        Spacer(Modifier.height(12.dp))
        ToggleRow(
            title = "包含背景色图层",
            hint = "按画布底色生成最底层背景",
            checked = ui.includeBackground,
            enabled = enabled,
            onCheckedChange = onBackground,
        )
        ToggleRow(
            title = "覆盖已存在文件",
            hint = "输出文件已存在时直接覆盖",
            checked = ui.overwrite,
            enabled = enabled,
            onCheckedChange = onOverwrite,
        )

        Spacer(Modifier.height(10.dp))
        Text("输出文件夹", style = MaterialTheme.typography.labelSmall, color = HsjColors.Muted)
        Row(
            Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(10.dp))
                .background(HsjColors.Field)
                .padding(start = 12.dp, end = 4.dp, top = 4.dp, bottom = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Outlined.Folder, contentDescription = null,
                tint = HsjColors.Cyan, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(8.dp))
            Text(
                ui.outputFolderName ?: "未选择",
                style = MaterialTheme.typography.bodyMedium,
                color = if (ui.outputTreeUri == null) HsjColors.Muted else HsjColors.Text,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
            TextButton(onClick = onPickOutput, enabled = enabled) { Text("选择") }
        }

        Spacer(Modifier.height(10.dp))
        OutlinedTextField(
            value = ui.outputName,
            onValueChange = onName,
            enabled = enabled,
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
            label = { Text("文件名（不含扩展名）") },
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
            colors = OutlinedTextFieldDefaults.colors(
                focusedTextColor = HsjColors.Text,
                unfocusedTextColor = HsjColors.Text,
                focusedBorderColor = HsjColors.Primary,
                unfocusedBorderColor = HsjColors.Border,
                focusedLabelColor = HsjColors.Cyan,
                unfocusedLabelColor = HsjColors.Hint,
                cursorColor = HsjColors.Cyan,
            ),
        )

        Spacer(Modifier.height(10.dp))
        val base = sanitizeOutputName(ui.outputName).ifBlank { "draft" }
        val preview = when (ui.format) {
            Format.PSD -> "$base.psd"
            Format.ORA -> "$base.ora"
            Format.BOTH -> "$base.psd   +   $base.ora"
        }
        Column(
            Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(12.dp))
                .background(HsjColors.Field)
                .padding(12.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("输出预览", style = MaterialTheme.typography.labelSmall,
                    color = HsjColors.Hint)
                Spacer(Modifier.weight(1f))
                Text(
                    when (ui.format) {
                        Format.PSD -> "PSD"
                        Format.ORA -> "ORA"
                        Format.BOTH -> "PSD + ORA"
                    },
                    style = MaterialTheme.typography.labelSmall,
                    color = HsjColors.Cyan,
                    fontWeight = FontWeight.Bold,
                )
            }
            Spacer(Modifier.height(4.dp))
            Text(
                preview,
                style = MaterialTheme.typography.bodySmall,
                color = HsjColors.Text2,
                fontFamily = FontFamily.Monospace,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
        }
        if (tooLargeForPsd) {
            Spacer(Modifier.height(6.dp))
            Text(
                "画布超过 30000 px，PSD 不可用；请改为 ORA。",
                style = MaterialTheme.typography.labelSmall,
                color = HsjColors.Error,
            )
        }
    }
}

@Composable
private fun ConvertBar(ui: UiState, job: JobState, onConvert: () -> Unit) {
    val draft = ui.draft
    val tooLargeForPsd = draft != null && ui.format.includesPsd &&
        (draft.canvasWidth > 30000 || draft.canvasHeight > 30000)
    val ready = draft != null && ui.outputTreeUri != null &&
        sanitizeOutputName(ui.outputName).isNotBlank() &&
        !job.running && !ui.loading && !tooLargeForPsd
    androidx.compose.material3.Surface(color = HsjColors.Background) {
        Column(Modifier.fillMaxWidth()) {
            HorizontalDivider(color = HsjColors.Border)
            Column(Modifier.padding(horizontal = 16.dp, vertical = 10.dp)) {
                Button(
                    onClick = onConvert,
                    enabled = ready,
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 50.dp),
                    shape = RoundedCornerShape(13.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = HsjColors.Primary,
                        contentColor = Color.White,
                        disabledContainerColor = HsjColors.Surface3,
                        disabledContentColor = HsjColors.Hint,
                    ),
                ) {
                    Icon(Icons.Outlined.AutoAwesome, contentDescription = null,
                        modifier = Modifier.size(19.dp))
                    Spacer(Modifier.width(8.dp))
                    Text(
                        if (job.running) "正在转换…" else "开始转换",
                        style = MaterialTheme.typography.titleMedium,
                    )
                }
                if (job.running) {
                    Spacer(Modifier.height(5.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            job.message,
                            style = MaterialTheme.typography.labelSmall,
                            color = HsjColors.Hint,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.weight(1f),
                        )
                        Text(
                            "${(job.fraction * 100).roundToInt()}%",
                            style = MaterialTheme.typography.labelSmall,
                            color = HsjColors.Cyan,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun ToggleRow(
    title: String,
    hint: String,
    checked: Boolean,
    enabled: Boolean,
    onCheckedChange: (Boolean) -> Unit,
) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(vertical = 3.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.bodyMedium, color = HsjColors.Text2)
            Text(hint, style = MaterialTheme.typography.labelSmall, color = HsjColors.Hint)
        }
        Switch(
            checked = checked,
            onCheckedChange = onCheckedChange,
            enabled = enabled,
            colors = androidx.compose.material3.SwitchDefaults.colors(
                checkedThumbColor = Color.White,
                checkedTrackColor = HsjColors.Primary,
                uncheckedThumbColor = Color(0xFFAAB3C7),
                uncheckedTrackColor = Color(0xFF2C3448),
            ),
        )
    }
}

@Composable
private fun Pill(text: String, color: Color = Color(0xFFC3B6FF)) {
    Text(
        text,
        style = MaterialTheme.typography.labelSmall,
        color = color,
        modifier = Modifier
            .clip(CircleShape)
            .background(color.copy(alpha = 0.12f))
            .padding(horizontal = 9.dp, vertical = 4.dp),
    )
}

@Composable
private fun ProgressCard(job: JobState, onCancel: () -> Unit) {
    if (!job.running && job.error == null && !job.cancelled) return
    SectionCard(
        title = if (job.running) "转换进度" else "任务状态",
        subtitle = stageLabel(job.stage),
    ) {
        if (job.running) {
            Text(job.message, style = MaterialTheme.typography.bodyMedium, color = HsjColors.Text2)
            Spacer(Modifier.height(8.dp))
            LinearProgressIndicator(
                progress = { job.fraction },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(6.dp)
                    .clip(CircleShape),
                color = HsjColors.Cyan,
                trackColor = HsjColors.Surface3,
            )
            Spacer(Modifier.height(6.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    if (job.total > 0) "${job.done}/${job.total}" else "准备中",
                    style = MaterialTheme.typography.labelSmall,
                    color = HsjColors.Hint,
                )
                Spacer(Modifier.weight(1f))
                TextButton(onClick = onCancel) { Text("取消") }
            }
        } else if (job.error != null) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Outlined.ErrorOutline, contentDescription = null,
                    tint = HsjColors.Error)
                Spacer(Modifier.width(8.dp))
                Text(job.error ?: "转换失败", style = MaterialTheme.typography.bodyMedium,
                    color = HsjColors.Error)
            }
        } else if (job.cancelled) {
            Text("转换已取消，未留下不完整文件。", style = MaterialTheme.typography.bodyMedium,
                color = HsjColors.Warning)
        }
    }
}

@Composable
private fun ResultCard(
    job: JobState,
    onOpen: (SavedOutput) -> Unit,
    onShare: (SavedOutput) -> Unit,
) {
    if (job.running || job.result.isEmpty()) return
    SectionCard(
        title = "转换完成",
        subtitle = if (job.durationMs > 0) "用时 ${"%.1f".format(job.durationMs / 1000.0)} 秒" else null,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            job.result.forEach { output ->
                Column(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(12.dp))
                        .background(HsjColors.Field)
                        .padding(12.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Outlined.CheckCircle, contentDescription = null,
                            tint = HsjColors.Success, modifier = Modifier.size(19.dp))
                        Spacer(Modifier.width(8.dp))
                        Text(
                            output.name,
                            style = MaterialTheme.typography.bodyMedium,
                            color = HsjColors.Text,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.weight(1f),
                        )
                    }
                    Spacer(Modifier.height(4.dp))
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                        TextButton(onClick = { onOpen(output) }) {
                            Icon(Icons.Outlined.OpenInNew, contentDescription = null,
                                modifier = Modifier.size(17.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("打开")
                        }
                        TextButton(onClick = { onShare(output) }) {
                            Icon(Icons.Outlined.Share, contentDescription = null,
                                modifier = Modifier.size(17.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("分享")
                        }
                    }
                }
            }
        }
        if (job.warnings.isNotEmpty()) {
            Spacer(Modifier.height(8.dp))
            job.warnings.take(3).forEach {
                Text("• $it", style = MaterialTheme.typography.labelSmall,
                    color = HsjColors.Warning)
            }
        }
    }
}

@Composable
private fun LayerTreeCard(ui: UiState, onToggle: (String) -> Unit) {
    val draft = ui.draft
    val rows = remember(ui.draft, ui.includeBackground, ui.expandedGroups) {
        flattenLayerRows(ui.displayRoots(), ui.expandedGroups)
    }
    val layerCount = remember(ui.draft, ui.includeBackground) {
        LayerTree.countLeaves(ui.displayRoots())
    }
    SectionCard(
        title = "图层结构",
        subtitle = "自上而下显示，与画世界Pro 图层面板一致",
        action = { Pill("$layerCount 层", HsjColors.Cyan) },
    ) {
        if (draft == null) {
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(140.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text("尚未载入草稿", style = MaterialTheme.typography.bodySmall,
                    color = HsjColors.Hint)
            }
        } else {
            Column(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .background(HsjColors.Field),
            ) {
                rows.forEachIndexed { index, row ->
                    LayerRowView(row, onToggle)
                    if (index != rows.lastIndex) {
                        HorizontalDivider(color = HsjColors.BorderSoft)
                    }
                }
            }
        }
    }
}

@Composable
private fun LayerRowView(row: LayerRow, onToggle: (String) -> Unit) {
    val layer = row.layer
    val hidden = !layer.visible
    val group = row.hasChildren
    val nameColor = when {
        hidden -> HsjColors.Muted
        group -> Color(0xFFC3B6FF)
        else -> HsjColors.Text
    }
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(enabled = group) { onToggle(displayKey(layer)) }
            .padding(start = (8 + row.depth * 16).dp, end = 10.dp, top = 8.dp, bottom = 8.dp)
            .alpha(if (hidden) 0.68f else 1f),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (group) {
            Icon(
                if (row.expanded) Icons.Outlined.KeyboardArrowDown
                else Icons.Outlined.KeyboardArrowRight,
                contentDescription = if (row.expanded) "折叠" else "展开",
                tint = HsjColors.Muted,
                modifier = Modifier.size(19.dp),
            )
        } else {
            Spacer(Modifier.width(19.dp))
        }
        Spacer(Modifier.width(4.dp))
        Icon(
            if (group) Icons.Outlined.Folder else Icons.Outlined.Layers,
            contentDescription = null,
            tint = if (group) HsjColors.PrimaryHi else HsjColors.Muted,
            modifier = Modifier.size(18.dp),
        )
        Spacer(Modifier.width(8.dp))
        Column(Modifier.weight(1f)) {
            Text(
                layer.name.ifBlank { "未命名" },
                style = MaterialTheme.typography.bodyMedium,
                color = nameColor,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            val secondary = buildList {
                add(if (layer.isGroup) "组" else "图层")
                add("${(layer.opacity * 100).roundToInt()}%")
                add(layer.blendName)
                clipLabel(layer).takeIf { it.isNotBlank() }?.let(::add)
                if (layer.isLockAlpha) add("锁透明")
                if (layer.isLock) add("锁定")
            }.joinToString(" · ")
            Text(
                secondary,
                style = MaterialTheme.typography.labelSmall,
                color = HsjColors.Hint,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        Icon(
            if (layer.visible) Icons.Outlined.Visibility else Icons.Outlined.VisibilityOff,
            contentDescription = if (layer.visible) "可见" else "隐藏",
            tint = if (layer.visible) HsjColors.Success else HsjColors.Muted,
            modifier = Modifier.size(18.dp),
        )
    }
}

@Composable
private fun LogCard(
    job: JobState,
    onShowAll: () -> Unit,
    onCopy: () -> Unit,
    onClear: () -> Unit,
) {
    val formatter = remember { SimpleDateFormat("HH:mm:ss", Locale.CHINA) }
    SectionCard(
        title = "运行日志",
        subtitle = "转换进度与结果",
        action = { TextButton(onClick = onShowAll) { Text("查看全部") } },
    ) {
        if (job.logs.isEmpty()) {
            Text("暂无日志", style = MaterialTheme.typography.bodySmall, color = HsjColors.Hint)
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                job.logs.takeLast(4).forEach { entry ->
                    LogLine(entry, formatter)
                }
            }
        }
        Spacer(Modifier.height(6.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            TextButton(onClick = onCopy) {
                Icon(Icons.Outlined.ContentCopy, contentDescription = null,
                    modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(4.dp))
                Text("复制")
            }
            TextButton(onClick = onClear) {
                Icon(Icons.Outlined.DeleteOutline, contentDescription = null,
                    modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(4.dp))
                Text("清空")
            }
        }
    }
}

@Composable
private fun LogLine(entry: LogEntry, formatter: SimpleDateFormat) {
    val color = when (entry.level) {
        LogLevel.ERROR -> HsjColors.Error
        LogLevel.WARN -> HsjColors.Warning
        LogLevel.SUCCESS -> HsjColors.Success
        LogLevel.INFO -> HsjColors.Text2
    }
    Row(Modifier.fillMaxWidth()) {
        Text(
            formatter.format(Date(entry.timestamp)),
            style = MaterialTheme.typography.labelSmall,
            color = HsjColors.Hint,
            fontFamily = FontFamily.Monospace,
        )
        Spacer(Modifier.width(7.dp))
        Text(
            entry.message,
            style = MaterialTheme.typography.labelSmall,
            color = color,
            maxLines = 3,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun LogSheet(
    logs: List<LogEntry>,
    onDismiss: () -> Unit,
    onCopy: () -> Unit,
    onClear: () -> Unit,
) {
    val formatter = remember { SimpleDateFormat("HH:mm:ss", Locale.CHINA) }
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        containerColor = HsjColors.Surface,
        contentColor = HsjColors.Text,
    ) {
        Column(
            Modifier
                .fillMaxHeight(0.82f)
                .fillMaxWidth()
                .padding(16.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("运行日志", style = MaterialTheme.typography.titleMedium,
                    color = HsjColors.Text)
                Spacer(Modifier.weight(1f))
                TextButton(onClick = onCopy) { Text("复制") }
                TextButton(onClick = onClear) { Text("清空") }
            }
            Spacer(Modifier.height(6.dp))
            if (logs.isEmpty()) {
                Text("暂无日志", color = HsjColors.Hint)
            } else {
                LazyColumn(Modifier.weight(1f)) {
                    items(logs) { entry ->
                        LogLine(entry, formatter)
                        Spacer(Modifier.height(3.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun AboutDialog(onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("关于 HSJ 转换器") },
        text = {
            Text(
                "版本 1.0.0\n\n" +
                    "把画世界Pro 的 .hsj 多图层草稿转换为 PSD / ORA，保留图层像素、名称、" +
                    "顺序、可见性、不透明度、混合模式与剪贴蒙版。\n\n" +
                    "转换在本机离线完成，不会上传草稿内容。\n\n" +
                    "说明：\n" +
                    "• PSD 中的图层组会扁平化\n" +
                    "• ORA 中的剪贴蒙版会烘焙进 alpha\n" +
                    "• Display P3 不嵌入 ICC，按 sRGB 解释\n" +
                    "• PSD 最大支持 30000×30000",
                style = MaterialTheme.typography.bodyMedium,
                color = HsjColors.Text2,
            )
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("关闭") } },
    )
}

private fun stageLabel(stage: Stage?): String? = when (stage) {
    Stage.PREPARE -> "读取与解析"
    Stage.DECODE -> "解码图层"
    Stage.LAYER_OUTPUT -> "解码并写入图层"
    Stage.COMPOSITE -> "合成"
    Stage.MERGED -> "生成合并预览"
    Stage.FINALIZE -> "完成"
    null -> null
}
