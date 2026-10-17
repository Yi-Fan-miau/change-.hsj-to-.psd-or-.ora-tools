package com.hsj.converter.data

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import androidx.documentfile.provider.DocumentFile
import java.io.File
import java.io.IOException

object SafFiles {
    fun displayName(context: Context, uri: Uri): String? {
        context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
            ?.use { cursor ->
                if (cursor.moveToFirst()) {
                    val idx = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    if (idx >= 0) return cursor.getString(idx)
                }
            }
        return uri.lastPathSegment?.substringAfterLast('/')
    }

    fun copyToCache(context: Context, uri: Uri, dir: File): File {
        dir.mkdirs()
        val rawName = displayName(context, uri) ?: "draft.hsj"
        val clean = rawName.replace(Regex("[\\\\/:*?\"<>|\\u0000-\\u001F]"), "_")
        val file = File(dir, "${System.currentTimeMillis()}_$clean")
        val input = context.contentResolver.openInputStream(uri)
            ?: throw IOException("无法读取所选文件")
        input.use { source ->
            file.outputStream().use { target -> source.copyTo(target, 256 * 1024) }
        }
        if (file.length() == 0L) {
            file.delete()
            throw IOException("所选文件为空")
        }
        return file
    }

    fun takePersistablePermission(context: Context, uri: Uri) {
        try {
            context.contentResolver.takePersistableUriPermission(
                uri, Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        } catch (_: SecurityException) {
            // Some providers only grant a transient permission.
        }
    }

    fun folderName(context: Context, treeUri: Uri): String? =
        DocumentFile.fromTreeUri(context, treeUri)?.name

    fun existingNames(context: Context, treeUri: Uri, names: List<String>): List<String> {
        val tree = DocumentFile.fromTreeUri(context, treeUri) ?: return emptyList()
        return names.filter { tree.findFile(it)?.exists() == true }
    }

    fun writeDocument(
        context: Context,
        treeUri: Uri,
        name: String,
        mime: String,
        source: File,
        overwrite: Boolean,
    ): Pair<String, Uri> {
        val tree = DocumentFile.fromTreeUri(context, treeUri)
            ?: throw IOException("输出目录不可访问，请重新选择")
        val existing = tree.findFile(name)
        if (existing != null && existing.exists()) {
            if (!overwrite) throw IOException("目标文件已存在：$name")
            if (!existing.delete()) throw IOException("无法覆盖已存在文件：$name")
        }
        val mimes = if (mime == "application/octet-stream") listOf(mime)
        else listOf(mime, "application/octet-stream")
        var doc: DocumentFile? = null
        var lastError: Throwable? = null
        for (candidate in mimes) {
            try {
                doc = tree.createFile(candidate, name)
                if (doc != null) break
            } catch (t: Throwable) {
                lastError = t
            }
        }
        val created = doc ?: throw IOException(
            "无法创建输出文件：$name${lastError?.message?.let { "（$it）" } ?: ""}")
        if (created.name != name) {
            runCatching { created.renameTo(name) }
        }
        try {
            val output = context.contentResolver.openOutputStream(created.uri, "wt")
                ?: context.contentResolver.openOutputStream(created.uri)
                ?: throw IOException("无法写入输出文件")
            output.use { target ->
                source.inputStream().use { input -> input.copyTo(target, 256 * 1024) }
            }
        } catch (t: Throwable) {
            runCatching { created.delete() }
            throw t
        }
        return (created.name ?: name) to created.uri
    }
}
