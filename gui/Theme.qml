pragma Singleton
import QtQuick

// Système de design — palette « Tokyo Night » (esprit NixOS / Hyprland).
// Singleton : tous les écrans lisent les mêmes couleurs/rayons/tailles.
QtObject {
    // Fonds
    readonly property color bg0: "#0f1117"   // fenêtre
    readonly property color bg1: "#161922"   // cartes / panneaux
    readonly property color bg2: "#1e2230"   // champs / survol
    readonly property color bg3: "#272b3a"   // survol appuyé

    // Accents
    readonly property color accent:  "#7aa2f7"  // bleu
    readonly property color accent2: "#bb9af7"  // violet
    readonly property color green:   "#9ece6a"
    readonly property color red:     "#f7768e"
    readonly property color yellow:  "#e0af68"
    readonly property color cyan:    "#7dcfff"

    // Texte
    readonly property color text:    "#c0caf5"
    readonly property color textDim: "#565f89"
    readonly property color textHi:  "#ffffff"

    // Bordures
    readonly property color border:  "#2a2f42"
    readonly property color borderHi: "#3b4261"

    // Rayons
    readonly property int radiusWin: 16
    readonly property int radiusCard: 14
    readonly property int radius: 10
    readonly property int radiusSm: 8

    // Espacements
    readonly property int pad: 18
    readonly property int gap: 12

    // Typo
    readonly property string font: "Segoe UI"
    readonly property int fsTitle: 22
    readonly property int fsHead: 16
    readonly property int fsBody: 14
    readonly property int fsSmall: 12

    // Durées d'animation
    readonly property int anim: 160
    readonly property int animSlow: 280
}
