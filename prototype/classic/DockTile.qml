import QtQuick
import QtQuick.Controls

// Original vector dock icons; no external fonts, assets, shaders or animation.
Button {
    id: tile
    required property string iconName
    width: 48
    height: 48
    readonly property color topTone: iconName === "Home" ? "#6fc3fb" :
        iconName === "Web" ? "#2385ef" :
        iconName === "Files" ? "#60c9fc" :
        iconName === "Photos" ? "#f48aaa" :
        iconName === "Notes" ? "#ffd976" :
        iconName === "Search" ? "#bf95f5" :
        iconName === "Terminal" ? "#55647e" : "#a4afc6"
    readonly property color bottomTone: iconName === "Home" ? "#156bc7" :
        iconName === "Web" ? "#13429e" :
        iconName === "Files" ? "#057ac9" :
        iconName === "Photos" ? "#bb377b" :
        iconName === "Notes" ? "#df8b24" :
        iconName === "Search" ? "#6639ba" :
        iconName === "Terminal" ? "#1d2744" : "#56647b"
    hoverEnabled: true
    Accessible.name: iconName + " (demonstration)"
    ToolTip.visible: hovered
    // Preview-only: icons are decorative until actual app launch services exist.
    ToolTip.text: iconName + " — demonstration only"

    background: Rectangle {
        radius: 12
        border.color: tile.hovered ? "#e5f3ff" : "#7297b7"
        border.width: 1
        gradient: Gradient {
            GradientStop { position: 0.0; color: tile.topTone }
            GradientStop { position: 1.0; color: tile.bottomTone }
        }
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 4
            height: 12
            radius: 8
            color: "#30ffffff"
        }
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
            ctx.strokeStyle = "#ffffff"
            ctx.fillStyle = "#ffffff"
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
                ctx.save()
                ctx.scale(0.42, 1)
                ctx.arc(0, 0, 12, 0, 2 * Math.PI)
                ctx.restore()
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
