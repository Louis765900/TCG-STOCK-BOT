import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import App 1.0

// Fenêtre principale : sans cadre, coins arrondis, sombre (esprit NixOS/Hyprland).
Window {
    id: win
    width: 1100
    height: 720
    minimumWidth: 880
    minimumHeight: 560
    visible: true
    color: "transparent"
    flags: Qt.Window | Qt.FramelessWindowHint
    title: "TCG Stock Bot"

    property int pageIndex: 0
    property bool montrerAssistant: premierLancement

    // Fermer la fenêtre la réduit dans la barre des tâches (le bot continue).
    // Pour quitter pour de bon : menu du tray → « Quitter ».
    onClosing: function(close) { close.accepted = false; win.hide() }

    // ---- Fond arrondi de la fenêtre ----------------------------------------
    Rectangle {
        id: cadre
        objectName: "cadre"
        anchors.fill: parent
        radius: Theme.radiusWin
        color: Theme.bg0
        border.width: 1
        border.color: Theme.borderHi

        // Lueur d'accent diffuse en haut (ambiance Hyprland).
        Rectangle {
            anchors { top: parent.top; left: parent.left; right: parent.right }
            height: 220
            radius: Theme.radiusWin
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(0.48, 0.64, 0.97, 0.10) }
                GradientStop { position: 1.0; color: "transparent" }
            }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 1
            spacing: 0

            TitleBar { Layout.fillWidth: true; win: win }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0

                // ---- Barre latérale ----------------------------------------
                Rectangle {
                    Layout.preferredWidth: 220
                    Layout.fillHeight: true
                    color: "transparent"
                    ColumnLayout {
                        anchors { fill: parent; margins: 12; topMargin: 4 }
                        spacing: 4

                        Repeater {
                            model: [
                                { ic: "🏠", nom: "Accueil" },
                                { ic: "📡", nom: "Surveillance" },
                                { ic: "✏️", nom: "Composer" },
                                { ic: "📜", nom: "Journal" },
                                { ic: "⚙️", nom: "Réglages" }
                            ]
                            delegate: NavButton {
                                Layout.fillWidth: true
                                icone: modelData.ic
                                label: modelData.nom
                                actif: win.pageIndex === index && !win.montrerAssistant
                                enabled: !win.montrerAssistant
                                opacity: win.montrerAssistant ? 0.4 : 1.0
                                onClicked: win.pageIndex = index
                            }
                        }

                        Item { Layout.fillHeight: true }

                        // Bandeau d'état en bas de la barre latérale.
                        Rectangle {
                            Layout.fillWidth: true
                            height: 1; color: Theme.border
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Layout.margins: 4
                            spacing: 8
                            StatusDot {
                                couleur: bridge.botActif() ? Theme.green : Theme.textDim
                                pulse: pulseTimer.actif
                            }
                            Text {
                                text: pulseTimer.actif ? "En marche" : "Arrêté"
                                color: Theme.textDim
                                font { family: Theme.font; pixelSize: Theme.fsSmall }
                            }
                            Item { Layout.fillWidth: true }
                            Text {
                                text: "v" + appVersion
                                color: Theme.textDim
                                font { family: Theme.font; pixelSize: Theme.fsSmall }
                            }
                        }
                    }
                }

                // ---- Zone de contenu ---------------------------------------
                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    color: Theme.bg0
                    radius: 0

                    // Pages (toutes instanciées : le journal continue de se remplir).
                    StackLayout {
                        anchors { fill: parent; margins: Theme.pad; topMargin: 6 }
                        currentIndex: win.pageIndex
                        visible: !win.montrerAssistant
                        PageAccueil {}
                        PageSurveillance {}
                        PageCompositeur {}
                        PageLogs {}
                        PageReglages {}
                    }

                    // Assistant de 1ère config (superposé au 1er lancement).
                    PageAssistant {
                        anchors.fill: parent
                        visible: win.montrerAssistant
                        onTermine: { win.montrerAssistant = false; win.pageIndex = 0 }
                    }
                }
            }
        }

        // ---- Poignée de redimensionnement (coin bas-droit) -----------------
        Item {
            anchors { right: parent.right; bottom: parent.bottom }
            width: 18; height: 18
            DragHandler {
                target: null
                onActiveChanged: if (active) win.startSystemResize(Qt.RightEdge | Qt.BottomEdge)
            }
            Canvas {
                anchors.fill: parent
                onPaint: {
                    var ctx = getContext("2d")
                    ctx.strokeStyle = Theme.borderHi
                    ctx.lineWidth = 1.4
                    for (var i = 1; i <= 3; i++) {
                        ctx.beginPath()
                        ctx.moveTo(width - i * 4, height - 2)
                        ctx.lineTo(width - 2, height - i * 4)
                        ctx.stroke()
                    }
                }
            }
        }
    }

    // ---- Suivi de l'état actif (pour la pastille de la barre latérale) -----
    QtObject {
        id: pulseTimer
        property bool actif: false
    }
    Connections {
        target: bridge
        function onBotBascule(running) { pulseTimer.actif = running }
        function onStatusChanged(s) { pulseTimer.actif = (s.running === true) }
    }

    // ---- Toast d'erreur ----------------------------------------------------
    Rectangle {
        id: toast
        property string message: ""
        anchors { bottom: parent.bottom; horizontalCenter: parent.horizontalCenter; bottomMargin: 28 }
        width: toastTxt.implicitWidth + 36
        height: 42
        radius: Theme.radius
        color: Theme.bg2
        border.width: 1; border.color: Theme.red
        opacity: 0
        visible: opacity > 0
        Text {
            id: toastTxt
            anchors.centerIn: parent
            text: toast.message
            color: Theme.text
            font { family: Theme.font; pixelSize: Theme.fsSmall }
        }
        Behavior on opacity { NumberAnimation { duration: Theme.anim } }
        Timer { id: toastTimer; interval: 4000; onTriggered: toast.opacity = 0 }
        function afficher(msg) { message = msg; opacity = 1; toastTimer.restart() }
    }
    Connections {
        target: bridge
        function onErreur(msg) { toast.afficher(msg) }
    }
}
