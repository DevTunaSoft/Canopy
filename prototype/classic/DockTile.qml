import QtQuick
import QtQuick.Controls

// Canopy-owned icon artwork. Preview dock items are intentionally not launchers.
// All painting is event-driven; there are no timers or continuous animations.
Button {
    id: tile
    required property string iconName
    property bool previewActive: false
    width: 54
    height: 61
    implicitWidth: 54
    implicitHeight: 61
    padding: 0
    hoverEnabled: true
    Accessible.name: iconName + " preview"
    Accessible.description: "Demonstration icon; application launching is not implemented"
    ToolTip.visible: hovered
    ToolTip.text: iconName + " — visual preview only"

    readonly property color tintTop: iconName === "Home" ? "#72b5e8"
        : iconName === "Files" ? "#70bce8"
        : iconName === "Browser" ? "#5c9bd0"
        : iconName === "Photos" ? "#d58ebe"
        : iconName === "Mail" ? "#6c9ce1"
        : iconName === "Calendar" ? "#f7f8f9" : "#8d9bac"
    readonly property color tintBottom: iconName === "Home" ? "#3164a6"
        : iconName === "Files" ? "#287fb9"
        : iconName === "Browser" ? "#2a527e"
        : iconName === "Photos" ? "#9b5fba"
        : iconName === "Mail" ? "#3067bf"
        : iconName === "Calendar" ? "#dce5ea" : "#526477"

    background: Item {
        Rectangle {
            id: tileSurface
            anchors.top: parent.top
            anchors.horizontalCenter: parent.horizontalCenter
            width: 52
            height: 52
            radius: 12
            gradient: Gradient {
                GradientStop { position: 0; color: tile.hovered ? Qt.lighter(tile.tintTop, 1.09) : tile.tintTop }
                GradientStop { position: 1; color: tile.tintBottom }
            }
            border.color: tile.hovered ? "#ffffff" : "#66ffffff"
            border.width: 1
        }
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 1
            width: 5
            height: 5
            radius: 2.5
            color: "#38536b"
            visible: tile.previewActive
        }
    }

    contentItem: Item {
        Canvas {
            id: artwork
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top
            anchors.topMargin: 10
            width: 32
            height: 32
            antialiasing: true
            renderTarget: Canvas.Image
            onPaint: {
                const ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                ctx.save()
                ctx.translate(16, 16)
                ctx.lineCap = "round"
                ctx.lineJoin = "round"
                ctx.lineWidth = 2.4
                ctx.strokeStyle = "#f8fbff"
                ctx.fillStyle = "#f8fbff"

                if (tile.iconName === "Home") {
                    ctx.beginPath()
                    ctx.moveTo(-12, -1); ctx.lineTo(0, -12); ctx.lineTo(12, -1)
                    ctx.lineTo(9, -1); ctx.lineTo(9, 11); ctx.lineTo(-9, 11)
                    ctx.lineTo(-9, -1); ctx.closePath(); ctx.fill()
                    ctx.fillStyle = "#4c89c5"
                    ctx.fillRect(-2.8, 3, 5.6, 8)
                } else if (tile.iconName === "Files") {
                    ctx.fillStyle = "#e7f5ff"
                    ctx.beginPath()
                    ctx.moveTo(-13, -8); ctx.lineTo(-4, -8); ctx.lineTo(0, -4)
                    ctx.lineTo(13, -4); ctx.lineTo(13, 11); ctx.lineTo(-13, 11)
                    ctx.closePath(); ctx.fill()
                    ctx.fillStyle = "#b7dff8"
                    ctx.fillRect(-11, -1, 22, 9)
                    ctx.strokeStyle = "#ffffff"
                    ctx.lineWidth = 1
                    ctx.beginPath()
                    ctx.moveTo(-10, 1); ctx.lineTo(10, 1); ctx.stroke()
                } else if (tile.iconName === "Browser") {
                    ctx.beginPath(); ctx.arc(0, 0, 12, 0, Math.PI*2); ctx.stroke()
                    ctx.beginPath()
                    ctx.moveTo(7, -8); ctx.lineTo(2, 6); ctx.lineTo(-7, 8)
                    ctx.lineTo(-2, -6); ctx.closePath()
                    ctx.fill()
                    ctx.fillStyle = "#20466e"
                    ctx.beginPath(); ctx.arc(0, 0, 1.9, 0, Math.PI*2); ctx.fill()
                } else if (tile.iconName === "Photos") {
                    const petalColors = ["#fff1d0", "#ffe3f3", "#d7f7ff", "#e6ebff",
                                         "#ffe3f3", "#fff1d0"]
                    for (let i = 0; i < 6; i++) {
                        const a = i * Math.PI/3
                        ctx.fillStyle = petalColors[i]
                        ctx.beginPath()
                        ctx.arc(Math.cos(a)*7, Math.sin(a)*7, 6, 0, Math.PI*2)
                        ctx.fill()
                    }
                    ctx.fillStyle = "#ffd27c"
                    ctx.beginPath(); ctx.arc(0, 0, 5, 0, Math.PI*2); ctx.fill()
                } else if (tile.iconName === "Mail") {
                    ctx.lineWidth = 2.1
                    ctx.beginPath()
                    ctx.moveTo(-12, -8); ctx.lineTo(12, -8); ctx.lineTo(12, 8)
                    ctx.lineTo(-12, 8); ctx.closePath(); ctx.stroke()
                    ctx.beginPath()
                    ctx.moveTo(-11, -7); ctx.lineTo(0, 2); ctx.lineTo(11, -7); ctx.stroke()
                } else if (tile.iconName === "Calendar") {
                    ctx.fillStyle = "#ffffff"
                    ctx.beginPath()
                    ctx.moveTo(-12, -12); ctx.lineTo(12, -12); ctx.lineTo(12, 12)
                    ctx.lineTo(-12, 12); ctx.closePath(); ctx.fill()
                    ctx.fillStyle = "#e66d67"
                    ctx.fillRect(-12, -12, 24, 7)
                    ctx.fillStyle = "#263d55"
                    ctx.font = "bold 15px sans-serif"
                    ctx.textAlign = "center"
                    ctx.textBaseline = "middle"
                    ctx.fillText("20", 0, 5)
                } else if (tile.iconName === "Settings") {
                    ctx.lineWidth = 2.6
                    ctx.beginPath(); ctx.arc(0, 0, 10, 0, Math.PI*2); ctx.stroke()
                    ctx.beginPath(); ctx.arc(0, 0, 4, 0, Math.PI*2); ctx.stroke()
                    for (let i = 0; i < 8; i++) {
                        const a = i * Math.PI/4
                        ctx.beginPath()
                        ctx.moveTo(Math.cos(a)*10, Math.sin(a)*10)
                        ctx.lineTo(Math.cos(a)*14, Math.sin(a)*14)
                        ctx.stroke()
                    }
                }
                ctx.restore()
            }
        }
    }
}
