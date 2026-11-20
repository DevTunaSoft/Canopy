import QtQuick
import QtQuick.Controls

// Original vector dock icons; no external fonts, assets, shaders or animation.
Button {
    id: tile
    required property string iconName
    width: 48
    height: 48
    hoverEnabled: true
    Accessible.name: iconName + " (demonstration)"
    ToolTip.visible: hovered
    // Preview-only: icons are decorative until actual app launch services exist.
    ToolTip.text: iconName + " — demonstration only"

    background: Rectangle {
        radius: 12
        color: tile.hovered ? "#ffffff" : (tile.iconName === "Home" ? "#d7e7fb" :
            tile.iconName === "Search" ? "#e7dff8" :
            tile.iconName === "Files" ? "#d5edee" :
            tile.iconName === "Settings" ? "#e3e6ee" :
            tile.iconName === "Web" ? "#c9e6f4" :
            tile.iconName === "Photos" ? "#f4d9e5" :
            tile.iconName === "Notes" ? "#f7e5b9" : "#d9e4df")
        border.color: tile.hovered ? "#95a9c2" : "#d0d7e1"
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
            ctx.strokeStyle = "#34445d"
            ctx.fillStyle = "#34445d"
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
            } else if (tile.iconName === "Web") {
                ctx.arc(0, 0, 12, 0, 2 * Math.PI)
                ctx.stroke()
                ctx.beginPath()
                ctx.ellipse(0, 0, 5, 12, 0, 0, 2 * Math.PI)
                ctx.moveTo(-11, 0)
                ctx.lineTo(11, 0)
                ctx.moveTo(-9, -6)
                ctx.lineTo(9, -6)
                ctx.moveTo(-9, 6)
                ctx.lineTo(9, 6)
                ctx.stroke()
            } else if (tile.iconName === "Photos") {
                ctx.rect(-12, -10, 24, 20)
                ctx.stroke()
                ctx.beginPath()
                ctx.arc(5, -4, 2.6, 0, 2 * Math.PI)
                ctx.fill()
                ctx.beginPath()
                ctx.moveTo(-10, 7)
                ctx.lineTo(-3, -1)
                ctx.lineTo(2, 4)
                ctx.lineTo(6, 0)
                ctx.lineTo(11, 7)
                ctx.stroke()
            } else if (tile.iconName === "Notes") {
                ctx.rect(-10, -12, 20, 24)
                ctx.stroke()
                ctx.beginPath()
                ctx.moveTo(-6, -5)
                ctx.lineTo(6, -5)
                ctx.moveTo(-6, 0)
                ctx.lineTo(6, 0)
                ctx.moveTo(-6, 5)
                ctx.lineTo(3, 5)
                ctx.stroke()
            } else if (tile.iconName === "Terminal") {
                ctx.rect(-13, -10, 26, 20)
                ctx.stroke()
                ctx.beginPath()
                ctx.moveTo(-8, -4)
                ctx.lineTo(-3, 0)
                ctx.lineTo(-8, 4)
                ctx.moveTo(0, 5)
                ctx.lineTo(8, 5)
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
