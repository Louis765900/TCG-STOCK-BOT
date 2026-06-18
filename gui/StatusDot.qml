import QtQuick
import App 1.0

// Pastille d'état avec un halo qui pulse quand c'est « actif ».
Item {
    id: root
    property color couleur: Theme.green
    property bool pulse: false
    implicitWidth: 12
    implicitHeight: 12

    Rectangle {
        id: halo
        anchors.centerIn: parent
        width: 12; height: 12; radius: 6
        color: root.couleur
        opacity: 0.35
        visible: root.pulse
        SequentialAnimation on scale {
            running: root.pulse
            loops: Animation.Infinite
            NumberAnimation { from: 1.0; to: 2.4; duration: 1100; easing.type: Easing.OutQuad }
            NumberAnimation { from: 2.4; to: 1.0; duration: 0 }
        }
        SequentialAnimation on opacity {
            running: root.pulse
            loops: Animation.Infinite
            NumberAnimation { from: 0.35; to: 0.0; duration: 1100 }
            NumberAnimation { from: 0.0; to: 0.35; duration: 0 }
        }
    }
    Rectangle {
        anchors.centerIn: parent
        width: 10; height: 10; radius: 5
        color: root.couleur
    }
}
