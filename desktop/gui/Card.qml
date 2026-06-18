import QtQuick
import App 1.0

// Panneau arrondi. Deux usages :
//  • « carte qui remplit » : on lui donne une hauteur (implicitHeight ou
//    Layout.fillHeight) et le contenu utilise anchors.fill: parent.
//  • « carte qui s'adapte au contenu » : pas de hauteur imposée, et le contenu
//    utilise width: parent.width (la carte prend alors la hauteur du contenu).
Rectangle {
    id: card
    default property alias content: zone.data
    property alias padding: zone.anchors.margins

    // Taille naturelle = contenu + marges (utilisée seulement si non imposée).
    implicitHeight: zone.implicitHeight + 2 * zone.anchors.margins
    implicitWidth: zone.implicitWidth + 2 * zone.anchors.margins

    radius: Theme.radiusCard
    color: Theme.bg1
    border.width: 1
    border.color: Theme.border

    // Reflet subtil en haut pour donner du relief.
    Rectangle {
        anchors { left: parent.left; right: parent.right; top: parent.top }
        height: parent.radius
        radius: parent.radius
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.035) }
            GradientStop { position: 1.0; color: "transparent" }
        }
    }

    Item {
        id: zone
        anchors.fill: parent
        anchors.margins: Theme.pad
        implicitWidth: childrenRect.width
        implicitHeight: childrenRect.height
    }
}
