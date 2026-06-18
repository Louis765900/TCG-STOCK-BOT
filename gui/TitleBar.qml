import QtQuick
import QtQuick.Window
import App 1.0

// Barre de titre personnalisée (fenêtre sans cadre) : déplacement + boutons.
Item {
    id: root
    property var win
    property string titre: "TCG Stock Bot"
    height: 46

    // Zone de déplacement de la fenêtre.
    DragHandler {
        target: null
        onActiveChanged: if (active && root.win) root.win.startSystemMove()
    }
    // Double-clic = maximiser / restaurer.
    TapHandler {
        onDoubleTapped: {
            if (!root.win) return
            root.win.visibility = (root.win.visibility === Window.Maximized)
                ? Window.Windowed : Window.Maximized
        }
    }

    Row {
        anchors { left: parent.left; verticalCenter: parent.verticalCenter; leftMargin: Theme.pad }
        spacing: 10
        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: 22; height: 22; radius: 7
            gradient: Gradient {
                orientation: Gradient.Vertical
                GradientStop { position: 0.0; color: Theme.accent }
                GradientStop { position: 1.0; color: Theme.accent2 }
            }
            Text { anchors.centerIn: parent; text: "◈"; color: Theme.bg0; font.pixelSize: 13; font.bold: true }
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.titre
            color: Theme.text
            font { family: Theme.font; pixelSize: Theme.fsBody; weight: Font.DemiBold }
        }
    }

    // Boutons fenêtre (réduire / fermer).
    Row {
        anchors { right: parent.right; verticalCenter: parent.verticalCenter; rightMargin: 10 }
        spacing: 4
        Repeater {
            model: [
                { glyphe: "—", danger: false, action: "min" },
                { glyphe: "✕", danger: true,  action: "close" }
            ]
            delegate: Item {
                width: 36; height: 30
                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 3
                    radius: Theme.radiusSm
                    color: bma.containsMouse ? (modelData.danger ? Theme.red : Theme.bg2) : "transparent"
                    Behavior on color { ColorAnimation { duration: Theme.anim } }
                    Text {
                        anchors.centerIn: parent
                        text: modelData.glyphe
                        color: (bma.containsMouse && modelData.danger) ? Theme.bg0 : Theme.text
                        font.pixelSize: 13
                    }
                }
                MouseArea {
                    id: bma
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        if (!root.win) return
                        if (modelData.action === "min") root.win.showMinimized()
                        else root.win.close()
                    }
                }
            }
        }
    }
}
