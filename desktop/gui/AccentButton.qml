import QtQuick
import QtQuick.Controls.Basic
import App 1.0

// Bouton arrondi animé. variant : "solid" (rempli accent) | "ghost" (contour) | "danger".
Button {
    id: ctrl
    property string variant: "solid"
    property color accentColor: Theme.accent

    implicitHeight: 38
    implicitWidth: Math.max(96, txt.implicitWidth + 34)
    font.family: Theme.font
    font.pixelSize: Theme.fsBody
    font.weight: Font.DemiBold
    hoverEnabled: true

    HoverHandler { cursorShape: Qt.PointingHandCursor }

    contentItem: Text {
        id: txt
        text: ctrl.text
        font: ctrl.font
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        color: ctrl.variant === "solid" ? Theme.bg0
                                        : (ctrl.variant === "danger" ? Theme.red : Theme.text)
    }

    background: Rectangle {
        radius: Theme.radius
        color: {
            if (!ctrl.enabled) return Theme.bg2
            if (ctrl.variant === "solid")
                return ctrl.down ? Qt.darker(ctrl.accentColor, 1.2)
                                 : (ctrl.hovered ? Qt.lighter(ctrl.accentColor, 1.1) : ctrl.accentColor)
            // ghost / danger : fond discret qui s'éclaire au survol
            return ctrl.down ? Theme.bg3 : (ctrl.hovered ? Theme.bg2 : "transparent")
        }
        border.width: ctrl.variant === "solid" ? 0 : 1
        border.color: ctrl.variant === "danger" ? Theme.red
                      : (ctrl.hovered ? Theme.borderHi : Theme.border)
        opacity: ctrl.enabled ? 1.0 : 0.6
        Behavior on color { ColorAnimation { duration: Theme.anim } }
        Behavior on border.color { ColorAnimation { duration: Theme.anim } }
    }

    scale: down ? 0.97 : 1.0
    Behavior on scale { NumberAnimation { duration: Theme.anim; easing.type: Easing.OutCubic } }
}
