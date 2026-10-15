(function () {
    "use strict";

    const STORAGE_KEY = "api_monitor_theme";
    const DEFAULT_THEME = "dark";

    function getTheme() {
        const saved = localStorage.getItem(STORAGE_KEY);

        if (saved === "light" || saved === "dark") {
            return saved;
        }

        return DEFAULT_THEME;
    }

    function removeLightTheme() {
        const lightTheme =
            document.getElementById("api-monitor-light-theme");

        if (lightTheme) {
            lightTheme.remove();
        }
    }

    function addLightTheme() {
        let lightTheme =
            document.getElementById("api-monitor-light-theme");

        if (!lightTheme) {
            lightTheme = document.createElement("link");

            lightTheme.id = "api-monitor-light-theme";
            lightTheme.rel = "stylesheet";
            lightTheme.href = "theme.css";

            document.head.appendChild(lightTheme);
        }
    }

    function applyTheme(theme, save) {
        const selectedTheme =
            theme === "light" ? "light" : "dark";

        if (selectedTheme === "light") {
            addLightTheme();
        } else {
            removeLightTheme();
        }

        document.documentElement.setAttribute(
            "data-theme",
            selectedTheme
        );

        if (save) {
            localStorage.setItem(
                STORAGE_KEY,
                selectedTheme
            );
        }

        const selector =
            document.getElementById("theme-select");

        if (selector) {
            selector.value = selectedTheme;
        }
    }

    window.setApiMonitorTheme = function (theme) {
        applyTheme(theme, true);
    };

    window.getApiMonitorTheme = function () {
        return getTheme();
    };

    document.addEventListener(
        "DOMContentLoaded",
        function () {
            applyTheme(getTheme(), false);
        }
    );
})();