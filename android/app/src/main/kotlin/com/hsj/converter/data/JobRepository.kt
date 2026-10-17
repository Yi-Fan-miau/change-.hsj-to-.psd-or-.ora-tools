package com.hsj.converter.data

import com.hsj.converter.core.LogLevel
import com.hsj.converter.core.Stage
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

object JobRepository {
    private val _state = MutableStateFlow(JobState())
    val state: StateFlow<JobState> = _state.asStateFlow()

    fun reset() {
        _state.value = JobState()
    }

    fun begin(total: Int = 0) {
        _state.value = JobState(
            running = true,
            stage = Stage.PREPARE,
            total = total,
            message = "准备转换",
        )
    }

    fun progress(stage: Stage, done: Int, total: Int, fraction: Float, message: String) {
        _state.update {
            it.copy(
                stage = stage,
                done = done,
                total = total,
                fraction = fraction.coerceIn(0f, 1f),
                message = message,
            )
        }
    }

    fun log(level: LogLevel, message: String) {
        val entry = LogEntry(System.currentTimeMillis(), level, message)
        _state.update { it.copy(logs = (it.logs + entry).takeLast(500)) }
    }

    fun success(outputs: List<SavedOutput>, warnings: List<String>, durationMs: Long) {
        _state.update {
            it.copy(
                running = false,
                fraction = 1f,
                stage = Stage.FINALIZE,
                message = "转换完成",
                result = outputs,
                warnings = warnings,
                durationMs = durationMs,
            )
        }
    }

    fun fail(message: String) {
        _state.update {
            it.copy(running = false, error = message, message = "转换失败")
        }
    }

    fun cancelled() {
        _state.update {
            it.copy(running = false, cancelled = true, message = "已取消")
        }
    }

    fun clearLogs() {
        _state.update { it.copy(logs = emptyList()) }
    }
}
