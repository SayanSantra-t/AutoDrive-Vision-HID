package com.example.ui.hud

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.platform.testTag
import com.example.model.DetectedObject
import com.example.model.LaneDetectionResult
import com.example.model.TelemetryData
import com.example.model.VehicleConfig
import kotlin.math.cos
import kotlin.math.sin

/**
 * Real-time AR HUD overlay drawn on top of the camera feed
 */
@Composable
fun HudOverlayCanvas(
    laneResult: LaneDetectionResult,
    detectedObjects: List<DetectedObject>,
    telemetry: TelemetryData,
    config: VehicleConfig,
    modifier: Modifier = Modifier
) {
    Canvas(
        modifier = modifier
            .fillMaxSize()
            .testTag("hud_overlay_canvas")
    ) {
        val canvasWidth = size.width
        val canvasHeight = size.height
        val horizonY = canvasHeight * config.cameraHorizonRatio

        // 1. Draw Horizon Grid & Pitch Marks
        drawHorizonHud(canvasWidth, canvasHeight, horizonY)

        // 2. Draw 3D Augmented Reality Road Corridor & Lane Splines
        drawAutonomousCorridor(canvasWidth, canvasHeight, horizonY, laneResult, telemetry.collisionWarning)

        // 3. Draw Detected Obstacle Bounding Boxes & Distance Tags
        drawDetectedObstacles(canvasWidth, canvasHeight, detectedObjects)

        // 4. Draw Dynamic Steering Heading Arc & Front Wheel Angle
        drawSteeringArc(canvasWidth, canvasHeight, telemetry.steeringAngleDeg)

        // 5. Draw Lane Center Deviation Indicator
        drawLateralOffsetGauge(canvasWidth, canvasHeight, laneResult.lateralOffsetMeters)
    }
}

private fun DrawScope.drawHorizonHud(width: Float, height: Float, horizonY: Float) {
    val midX = width / 2f

    // Horizon line with dashed styling
    drawLine(
        color = Color(0x3300E5FF),
        start = Offset(width * 0.15f, horizonY),
        end = Offset(width * 0.85f, horizonY),
        strokeWidth = 1.5f,
        pathEffect = PathEffect.dashPathEffect(floatArrayOf(10f, 10f), 0f)
    )

    // Vanishing Point Reticle
    drawCircle(
        color = Color(0x6600E5FF),
        radius = 6f,
        center = Offset(midX, horizonY),
        style = Stroke(width = 1.5f)
    )
    drawLine(
        color = Color(0x9900E5FF),
        start = Offset(midX - 14f, horizonY),
        end = Offset(midX + 14f, horizonY),
        strokeWidth = 1.5f
    )
    drawLine(
        color = Color(0x9900E5FF),
        start = Offset(midX, horizonY - 14f),
        end = Offset(midX, horizonY + 14f),
        strokeWidth = 1.5f
    )
}

private fun DrawScope.drawAutonomousCorridor(
    width: Float,
    height: Float,
    horizonY: Float,
    lane: LaneDetectionResult,
    collisionWarning: Boolean
) {
    val leftPts = lane.leftLanePoints
    val rightPts = lane.rightLanePoints

    if (leftPts.isNotEmpty() && rightPts.isNotEmpty()) {
        val corridorPath = Path().apply {
            // Start at bottom left
            moveTo(leftPts.first().first * width, leftPts.first().second * height)

            // Trace up left boundary
            for (pt in leftPts) {
                lineTo(pt.first * width, pt.second * height)
            }

            // Trace across top to right boundary
            val topR = rightPts.last()
            lineTo(topR.first * width, topR.second * height)

            // Trace down right boundary
            for (i in rightPts.indices.reversed()) {
                val pt = rightPts[i]
                lineTo(pt.first * width, pt.second * height)
            }

            close()
        }

        // Fill Corridor with dynamic gradient
        val corridorColorTop = when {
            collisionWarning -> Color(0x44EF4444)
            lane.isRoadDepartureThreat -> Color(0x44F59E0B)
            else -> Color(0x2200E5FF)
        }
        val corridorColorBottom = when {
            collisionWarning -> Color(0x66EF4444)
            lane.isRoadDepartureThreat -> Color(0x66F59E0B)
            else -> Color(0x4410B981)
        }

        drawPath(
            path = corridorPath,
            brush = Brush.verticalGradient(
                colors = listOf(corridorColorTop, corridorColorBottom),
                startY = horizonY,
                endY = height
            )
        )

        // Draw Left Lane boundary line
        val leftLinePath = Path().apply {
            moveTo(leftPts.first().first * width, leftPts.first().second * height)
            for (pt in leftPts) lineTo(pt.first * width, pt.second * height)
        }
        drawPath(
            path = leftLinePath,
            color = if (collisionWarning) Color(0xFFFF5252) else Color(0xFF00E5FF),
            style = Stroke(width = 3.5f, cap = StrokeCap.Round)
        )

        // Draw Right Lane boundary line
        val rightLinePath = Path().apply {
            moveTo(rightPts.first().first * width, rightPts.first().second * height)
            for (pt in rightPts) lineTo(pt.first * width, pt.second * height)
        }
        drawPath(
            path = rightLinePath,
            color = if (collisionWarning) Color(0xFFFF5252) else Color(0xFF00E5FF),
            style = Stroke(width = 3.5f, cap = StrokeCap.Round)
        )

        // Draw Center Waypoints
        for (pt in lane.centerTrajectory) {
            val px = pt.first * width
            val py = pt.second * height
            drawCircle(
                color = if (collisionWarning) Color(0xFFEF4444) else Color(0xFF76FF03),
                radius = 3.5f,
                center = Offset(px, py)
            )
        }
    }
}

private fun DrawScope.drawDetectedObstacles(
    width: Float,
    height: Float,
    detectedObjects: List<DetectedObject>
) {
    val paint = android.graphics.Paint().apply {
        isAntiAlias = true
        textSize = 28f
        typeface = android.graphics.Typeface.DEFAULT_BOLD
    }

    for (obj in detectedObjects) {
        val left = obj.left * width
        val top = obj.top * height
        val right = obj.right * width
        val bottom = obj.bottom * height
        val boxWidth = right - left
        val boxHeight = bottom - top

        val boxColor = if (obj.isCollisionThreat) Color(0xFFFF1744) else Color(obj.objectClass.colorHex)

        // Draw corner brackets around target
        val bracketLen = (boxWidth * 0.25f).coerceIn(12f, 35f)
        val strokeW = if (obj.isCollisionThreat) 3.5f else 2.5f

        // Top-Left
        drawLine(boxColor, Offset(left, top), Offset(left + bracketLen, top), strokeW)
        drawLine(boxColor, Offset(left, top), Offset(left, top + bracketLen), strokeW)

        // Top-Right
        drawLine(boxColor, Offset(right, top), Offset(right - bracketLen, top), strokeW)
        drawLine(boxColor, Offset(right, top), Offset(right, top + bracketLen), strokeW)

        // Bottom-Left
        drawLine(boxColor, Offset(left, bottom), Offset(left + bracketLen, bottom), strokeW)
        drawLine(boxColor, Offset(left, bottom), Offset(left, bottom - bracketLen), strokeW)

        // Bottom-Right
        drawLine(boxColor, Offset(right, bottom), Offset(right - bracketLen, bottom), strokeW)
        drawLine(boxColor, Offset(right, bottom), Offset(right, bottom - bracketLen), strokeW)

        // Semi-transparent target fill
        drawRect(
            color = boxColor.copy(alpha = if (obj.isCollisionThreat) 0.25f else 0.08f),
            topLeft = Offset(left, top),
            size = Size(boxWidth, boxHeight)
        )

        // Target Info Badge with Class, Confidence %, Distance, and TTC
        val confPct = (obj.confidence * 100).toInt()
        val tagText = "${obj.objectClass.label} ($confPct%) ${String.format("%.1fm", obj.distanceMeters)}"
        val ttcText = if (obj.timeToCollisionSec < 10f) " | TTC: ${String.format("%.1fs", obj.timeToCollisionSec)}" else ""
        val threatBadge = if (obj.isCollisionThreat) " [AEB THREAT]" else ""
        val fullLabel = "$tagText$ttcText$threatBadge"

        drawContext.canvas.nativeCanvas.apply {
            paint.color = if (obj.isCollisionThreat) android.graphics.Color.argb(230, 185, 28, 28) else android.graphics.Color.argb(210, 15, 23, 42)
            drawRect(left, top - 38f, left + paint.measureText(fullLabel) + 18f, top, paint)

            paint.color = if (obj.isCollisionThreat) android.graphics.Color.WHITE else android.graphics.Color.CYAN
            drawText(fullLabel, left + 9f, top - 11f, paint)
        }
    }
}

private fun DrawScope.drawSteeringArc(width: Float, height: Float, steeringDeg: Float) {
    val midX = width / 2f
    val bottomY = height - 30f
    val radius = 80f

    // Neutral arc
    drawArc(
        color = Color(0x3300E5FF),
        startAngle = 180f,
        sweepAngle = 180f,
        useCenter = false,
        topLeft = Offset(midX - radius, bottomY - radius),
        size = Size(radius * 2, radius * 2),
        style = Stroke(width = 4f, cap = StrokeCap.Round)
    )

    // Dynamic steering pointer angle
    val angleRad = Math.toRadians((270f + steeringDeg).toDouble())
    val pointerX = midX + (radius * cos(angleRad)).toFloat()
    val pointerY = bottomY + (radius * sin(angleRad)).toFloat()

    // Line from center to arc
    drawLine(
        color = Color(0xFF00E5FF),
        start = Offset(midX, bottomY),
        end = Offset(pointerX, pointerY),
        strokeWidth = 4f,
        cap = StrokeCap.Round
    )

    drawCircle(
        color = Color(0xFF76FF03),
        radius = 5f,
        center = Offset(pointerX, pointerY)
    )
}

private fun DrawScope.drawLateralOffsetGauge(width: Float, height: Float, offsetMeters: Float) {
    val midX = width / 2f
    val gaugeY = height - 10f
    val gaugeWidth = 140f

    // Background bar
    drawLine(
        color = Color(0x33FFFFFF),
        start = Offset(midX - gaugeWidth / 2, gaugeY),
        end = Offset(midX + gaugeWidth / 2, gaugeY),
        strokeWidth = 2f
    )

    // Center tick
    drawLine(
        color = Color(0x8800E5FF),
        start = Offset(midX, gaugeY - 6f),
        end = Offset(midX, gaugeY + 6f),
        strokeWidth = 2f
    )

    // Dynamic indicator dot
    val indicatorX = (midX + (offsetMeters * 40f)).coerceIn(midX - gaugeWidth / 2, midX + gaugeWidth / 2)
    drawCircle(
        color = if (kotlin.math.abs(offsetMeters) > 0.4f) Color(0xFFEF4444) else Color(0xFF00E5FF),
        radius = 4.5f,
        center = Offset(indicatorX, gaugeY)
    )
}
