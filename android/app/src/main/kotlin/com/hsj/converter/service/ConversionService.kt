package com.hsj.converter.service

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.Uri
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import com.hsj.converter.MainActivity
import com.hsj.converter.R
import com.hsj.converter.codec.ZstdJniBlockDecoder
import com.hsj.converter.core.ConversionCancelledException
import com.hsj.converter.core.ConversionEngine
import com.hsj.converter.core.ConvertRequest
import com.hsj.converter.core.EngineListener
import com.hsj.converter.core.Format
import com.hsj.converter.core.LogLevel
import com.hsj.converter.core.OutputFile
import com.hsj.converter.core.Stage
import com.hsj.converter.data.JobRepository
import com.hsj.converter.data.SavedOutput
import com.hsj.converter.data.SafFiles
import com.hsj.converter.data.extension
import com.hsj.converter.data.formatMime
import java.io.File

class ConversionService : Service(), EngineListener {
    private val tag = "HSJConverter"

    companion object {
        const val ACTION_START = "com.hsj.converter.action.START"
        const val ACTION_CANCEL = "com.hsj.converter.action.CANCEL"
        const val EXTRA_INPUT = "input"
        const val EXTRA_TREE = "tree"
        const val EXTRA_BASE_NAME = "baseName"
        const val EXTRA_FORMAT = "format"
        const val EXTRA_INCLUDE_BG = "includeBg"
        const val EXTRA_OVERWRITE = "overwrite"
        private const val CHANNEL_ID = "hsj_conversion"
        private const val NOTIFICATION_ID = 1001
    }

    private var worker: Thread? = null
    @Volatile private var cancelRequested = false
    private var wakeLock: PowerManager.WakeLock? = null
    private var lastNotificationPercent = -1

    override fun onCreate() {
        super.onCreate()
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent == null) {
            stopSelf()
            return START_NOT_STICKY
        }
        when (intent.action) {
            ACTION_CANCEL -> {
                cancelRequested = true
                JobRepository.log(LogLevel.WARN, "正在取消转换…")
                updateNotification("正在取消…", 0f, indeterminate = true)
                if (worker?.isAlive != true) stopSelf()
                return START_NOT_STICKY
            }
            ACTION_START -> {
                Log.i(tag, "service start")
                if (worker?.isAlive == true) return START_NOT_STICKY
                cancelRequested = false
                startForegroundCompat(buildNotification("准备转换…", 0f, indeterminate = true))
                acquireWakeLock()
                val copied = Intent(intent)
                worker = Thread({ runJob(copied) }, "hsj-conversion").apply { start() }
                return START_NOT_STICKY
            }
        }
        stopSelf()
        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        cancelRequested = true
        releaseWakeLock()
        super.onDestroy()
    }

    private fun runJob(intent: Intent) {
        val inputPath = intent.getStringExtra(EXTRA_INPUT)
        val treeString = intent.getStringExtra(EXTRA_TREE)
        val baseName = intent.getStringExtra(EXTRA_BASE_NAME) ?: "draft"
        val format = runCatching {
            Format.valueOf(intent.getStringExtra(EXTRA_FORMAT) ?: Format.PSD.name)
        }.getOrDefault(Format.PSD)
        val includeBg = intent.getBooleanExtra(EXTRA_INCLUDE_BG, true)
        val overwrite = intent.getBooleanExtra(EXTRA_OVERWRITE, false)
        val workDir = File(cacheDir, "jobs/${System.currentTimeMillis()}").apply { mkdirs() }
        val inputs = inputPath?.let(::File)
        val saved = ArrayList<SavedOutput>()
        var duration = 0L

        try {
            if (inputs == null || !inputs.isFile) throw IllegalArgumentException("输入文件已失效")
            if (treeString == null) throw IllegalArgumentException("未选择输出目录")
            JobRepository.begin()
            Log.i(tag, "job input=${inputs.name} format=$format bg=$includeBg overwrite=$overwrite")
            JobRepository.log(LogLevel.INFO, "开始转换：${inputs.name}")
            updateNotification("准备转换…", 0f, indeterminate = true)

            val psdFile = if (format.includesPsd) File(workDir, "out.psd") else null
            val oraFile = if (format.includesOra) File(workDir, "out.ora") else null
            val request = ConvertRequest(format, includeBg, psdFile, oraFile, workDir)
            val result = ConversionEngine(ZstdJniBlockDecoder(), this).convert(inputs, request)
            duration = result.durationMs
            result.warnings.forEach { JobRepository.log(LogLevel.WARN, it) }

            val treeUri = Uri.parse(treeString)
            for (output in result.outputs) {
                val name = "$baseName.${extension(output.format)}"
                JobRepository.log(LogLevel.INFO, "保存 ${output.file.name} → $name")
                val (actualName, uri) = SafFiles.writeDocument(
                    this, treeUri, name, formatMime(output.format), output.file, overwrite)
                saved += SavedOutput(actualName, uri, output.format)
            }
            JobRepository.success(saved, result.warnings, duration)
            Log.i(tag, "job done outputs=${saved.map { it.name }} duration=${duration}ms warnings=${result.warnings.size}")
            JobRepository.log(LogLevel.SUCCESS, "转换完成，用时 ${duration / 1000.0} 秒")
            showCompletion(saved)
        } catch (_: ConversionCancelledException) {
            Log.i(tag, "job cancelled")
            JobRepository.cancelled()
            JobRepository.log(LogLevel.WARN, "转换已取消")
            showCompletion(emptyList(), "已取消")
        } catch (t: Throwable) {
            val message = friendlyError(t)
            Log.e(tag, "job failed", t)
            JobRepository.fail(message)
            JobRepository.log(LogLevel.ERROR, message)
            showCompletion(emptyList(), "转换失败")
        } finally {
            releaseWakeLock()
            runCatching { workDir.deleteRecursively() }
            stopForegroundCompat()
            stopSelf()
        }
    }

    private fun friendlyError(t: Throwable): String {
        val raw = t.message?.takeIf { it.isNotBlank() } ?: t::class.java.simpleName
        return if (t is OutOfMemoryError) {
            "内存不足，请关闭其他应用后重试"
        } else raw
    }

    override fun onProgress(stage: Stage, done: Int, total: Int, fraction: Float, message: String) {
        JobRepository.progress(stage, done, total, fraction, message)
        Log.d(tag, "progress ${(fraction * 100).toInt()}% ${stage.name} $done/$total $message")
        updateNotification(message, fraction, indeterminate = false)
    }

    override fun onLog(level: LogLevel, message: String) {
        Log.i(tag, "${level.name}: $message")
        JobRepository.log(level, message)
    }

    override fun isCancelled(): Boolean = cancelRequested

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = getSystemService(NotificationManager::class.java)
            val channel = NotificationChannel(
                CHANNEL_ID,
                getString(R.string.notification_channel_name),
                NotificationManager.IMPORTANCE_LOW,
            ).apply {
                description = getString(R.string.notification_channel_desc)
                setShowBadge(false)
            }
            manager.createNotificationChannel(channel)
        }
    }

    private fun contentIntent(): PendingIntent {
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        return PendingIntent.getActivity(
            this, 1, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    }

    private fun cancelIntent(): PendingIntent {
        val intent = Intent(this, ConversionService::class.java).setAction(ACTION_CANCEL)
        return PendingIntent.getService(
            this, 2, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    }

    private fun buildNotification(
        text: String,
        fraction: Float,
        indeterminate: Boolean,
    ): android.app.Notification {
        val builder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("HSJ 转换器")
            .setContentText(text)
            .setContentIntent(contentIntent())
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .addAction(R.drawable.ic_notification, "取消", cancelIntent())
        if (indeterminate) {
            builder.setProgress(0, 0, true)
        } else {
            builder.setProgress(100, (fraction * 100).toInt().coerceIn(0, 100), false)
        }
        return builder.build()
    }

    private fun updateNotification(text: String, fraction: Float, indeterminate: Boolean) {
        val percent = (fraction * 100).toInt()
        if (!indeterminate && percent == lastNotificationPercent) return
        lastNotificationPercent = percent
        val manager = getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, buildNotification(text, fraction, indeterminate))
    }

    private fun startForegroundCompat(notification: android.app.Notification) {
        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
        } else 0
        ServiceCompat.startForeground(this, NOTIFICATION_ID, notification, type)
    }

    private fun stopForegroundCompat() {
        ServiceCompat.stopForeground(this, Service.STOP_FOREGROUND_DETACH)
    }

    private fun showCompletion(outputs: List<SavedOutput>, title: String = "转换完成") {
        val text = when {
            outputs.isNotEmpty() -> outputs.joinToString("、") { it.name }
            else -> title
        }
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(text)
            .setContentIntent(contentIntent())
            .setAutoCancel(true)
            .setOngoing(false)
            .setOnlyAlertOnce(true)
            .build()
        getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, notification)
    }

    private fun acquireWakeLock() {
        if (wakeLock?.isHeld == true) return
        val power = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "HSJConverter:convert").apply {
            setReferenceCounted(false)
            acquire(60 * 60 * 1000L)
        }
    }

    private fun releaseWakeLock() {
        runCatching { if (wakeLock?.isHeld == true) wakeLock?.release() }
        wakeLock = null
    }
}
