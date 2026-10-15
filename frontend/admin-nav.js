(function () {
    "use strict";

    const ADMIN_OVERVIEW_URL = "/app/admin_overview.html";
    const ADMIN_API_URL = "/api/admin/system-overview/";

    function getToken() {
        return (
            localStorage.getItem("access_token") ||
            localStorage.getItem("access") ||
            ""
        );
    }

    function getCurrentPage() {
        return window.location.pathname.split("/").pop().toLowerCase();
    }

    function addAdminNavigation() {
        const navigation =
            document.querySelector(".nav") ||
            document.querySelector(".navigation");

        if (!navigation) {
            return;
        }

        if (
            navigation.querySelector(
                'a[href="/app/admin_overview.html"]'
            )
        ) {
            return;
        }

        if (getCurrentPage() === "admin_overview.html") {
            return;
        }

        const sidebar = navigation.parentElement;

        if (!sidebar) {
            return;
        }

        /* Admin section label */
        const adminLabel = document.createElement("div");

        if (navigation.classList.contains("nav")) {
            adminLabel.className = "nav-title";
        } else {
            adminLabel.className = "nav-title";
        }

        adminLabel.textContent = "ADMINISTRATION";

        /* Admin navigation link */
        const adminLink = document.createElement("a");

        adminLink.href = ADMIN_OVERVIEW_URL;

        /*
         * Do not add custom styling here.
         * The existing .nav a / .navigation .nav-item
         * styles should control the appearance.
         */
        if (navigation.classList.contains("navigation")) {
            adminLink.className = "nav-item";
        }

        adminLink.innerHTML =
            '<span class="nav-icon">▦</span>' +
            '<span>System Overview</span>';

        /* Put the admin section before the normal navigation */
        sidebar.insertBefore(adminLabel, navigation);

        /* Put the admin link inside the existing navigation */
        navigation.insertBefore(
            adminLink,
            navigation.firstElementChild
        );
    }

    async function checkAdminAccess() {
        const token = getToken();

        if (!token) {
            return;
        }

        try {
            const response = await fetch(
                ADMIN_API_URL,
                {
                    method: "GET",
                    headers: {
                        "Authorization": "Bearer " + token,
                        "Accept": "application/json"
                    }
                }
            );

            if (response.status === 200) {
                addAdminNavigation();
            }
        } catch (error) {
            /*
             * Normal users simply do not receive
             * the administrator navigation item.
             */
        }
    }

    /*
     * Wait until the sidebar exists before modifying it.
     */
    if (document.readyState === "loading") {
        document.addEventListener(
            "DOMContentLoaded",
            checkAdminAccess
        );
    } else {
        checkAdminAccess();
    }
})();