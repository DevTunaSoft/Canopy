import QtQuick
import QtQuick.Controls

// Original vector dock icons; no external fonts, assets, shaders or animation.
Button {
    id: tile
    required property string iconName
    width: 52
    height: 52
    hoverEnabled: true
    Accessible.name: iconName + " (demonstration)"
    ToolTip.visible: hovered
    ToolTip.text: iconName + " — demonstration only"

    background: Rectangle {
        radius: 13
        color: tile.hovered ? "#405d7b" : "#2c425a"
        border.color: tile.hovered ? "#7797b4" : "#49617a"
        border.width: 1
    }

    contentItem: Canvas {
        id: artwork
        width: 30
        height: 30
        onPaint: {
            const ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            ctx.save()
            ctx.translate(width / 2, height / 2)
            ctx.scale(Math.min(width, height) / 32, Math.min(width, height) / 32)
            ctx.strokeStyle = "#f6f8fc"
            ctx.fillStyle = "#f6f8fc"
            ctx.lineWidth = 2.2
            ctx.lineCap = "round"
            ctx.lineJoin = "round"
            ctx.beginPath()
            if (tile.iconName === "Home") {
                ctx.moveTo(-11, -1)
                ctx.lineTo(0, -11)
                ctx.lineTo(11, -1)
                ctx.moveTo(-8, -3)
                ctx.lineTo(-8, 10)
                ctx.lineTo(8, 10)
                ctx.lineTo(8, -3)
                ctx.moveTo(-3, 10)
                ctx.lineTo(-3, 2)
                ctx.lineTo(3, 2)
                ctx.lineTo(3, 10)
                ctx.stroke()
            } else if (tile.iconName === "Search") {
                ctx.arc(-3, -3, 8, 0, 2 * Math.PI)
                ctx.moveTo(3, 3)
                ctx.lineTo(12, 12)
                ctx.stroke()
            } else if (tile.iconName === "Files") {
                ctx.moveTo(-12, -7)
                ctx.lineTo(-3, -7)
                ctx.lineTo(0, -4)
                ctx.lineTo(11, -4)
                ctx.lineTo(11, 9)
                ctx.lineTo(-12, 9)
                ctx.closePath()
                ctx.stroke()
                ctx.beginPath()
                ctx.moveTo(-12, -3)
                ctx.lineTo(-12, -10)
                ctx.lineTo(-4, -10)
                ctx.lineTo(-1, -7)
                ctx.stroke()
            } else if (tile.iconName === "Settings") {
                ctx.arc(0, 0, 9, 0, 2 * Math.PI)
                ctx.stroke()
                ctx.beginPath()
                ctx.arc(0, 0, 3.3, 0, 2 * Math.PI)
                ctx.stroke()
                for (let i = 0; i < 8; ++i) {
                    const angle = i * Math.PI / 4
                    ctx.beginPath()
                    ctx.moveTo(Math.cos(angle) * 10, Math.sin(angle) * 10)
                    ctx.lineTo(Math.cos(angle) * 13, Math.sin(angle) * 13)
                    ctx.stroke()
                }
            }
            ctx.restore()
        }
    }
}
