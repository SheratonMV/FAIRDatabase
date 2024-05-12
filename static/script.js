    document.addEventListener("DOMContentLoaded", function() {
        // Check if there's a stored state for the sidebar
        const isCollapsed = localStorage.getItem("sidebarCollapsed") === "true";
        const body = document.getElementById("body");
        const sidebar = document.getElementById("sidebar");
        const pageContent = document.getElementById("page-content");
        const collapseIcon = document.getElementById("collapseIcon");
        const profilePic = document.getElementById("profilePic");
        const name = document.getElementById("profileName");

        // Apply the stored state or default state
        if (isCollapsed) {
            body.classList.add("collapsed");
            sidebar.style.width = "70px";
            pageContent.style.marginLeft = "70px";
            collapseIcon.classList.remove("fa-chevron-left");
            collapseIcon.classList.add("fa-chevron-right");
            profilePic.style.width = "35px"; // Set collapsed width
            profilePic.style.height = "35px"; // Set collapsed height
            name.style.display = "none"; // Hide the name
        }
    });

    function toggleSidebar() {
        const body = document.getElementById("body");
        const sidebar = document.getElementById("sidebar");
        const pageContent = document.getElementById("page-content");
        const collapseIcon = document.getElementById("collapseIcon");
        const profilePic = document.getElementById("profilePic");
        const name = document.getElementById("profileName");
        const isCollapsed = body.classList.contains("collapsed");

        // Toggle the collapsed class
        body.classList.toggle("collapsed");

        // Update the sidebar state in localStorage
        localStorage.setItem("sidebarCollapsed", !isCollapsed);

        // Apply styles based on the current state
        if (!isCollapsed) {
            sidebar.style.width = "70px";
            pageContent.style.marginLeft = "70px";
            collapseIcon.classList.remove("fa-chevron-left");
            collapseIcon.classList.add("fa-chevron-right");
            profilePic.style.width = "35px"; // Set collapsed width
            profilePic.style.height = "35px"; // Set collapsed height
            name.style.display = "none"; // Hide the name
        } else {
            sidebar.style.width = "250px";
            pageContent.style.marginLeft = "250px";
            collapseIcon.classList.remove("fa-chevron-right");
            collapseIcon.classList.add("fa-chevron-left");
            profilePic.style.width = "80px"; // Set original width
            profilePic.style.height = "80px"; // Set original height
            name.style.display = "block"; // Show the name
        }
    }