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

document.addEventListener('DOMContentLoaded', () => {
    $('.alert').alert()
});

document.addEventListener('DOMContentLoaded', function () {
    const rowLimitSelect = document.getElementById('rowLimit');
    const tableBody = document.getElementById('tableBody');
    const toggleRowsButton = document.getElementById('toggleRows');
    const resetButton = document.getElementById('reset-button');
    const searchForm = document.getElementById('search');
    const searchInput = document.getElementById('search-focus');
    const activeCheckbox = document.getElementById('flexCheckActive');
    const nonActiveCheckbox = document.getElementById('flexCheckNonActive1');

    let currentLimit = parseInt(rowLimitSelect.value);

    function updateVisibleRows(limit) {
        const rows = tableBody.querySelectorAll('tr');
        rows.forEach((row, index) => {
            row.classList.toggle('hidden-row', index >= limit);
        });
        currentLimit = limit;
        toggleRowsButton.textContent = limit >= rows.length ? 'Collapse' : 'Load More';
    }

    rowLimitSelect.addEventListener('change', function () {
        updateVisibleRows(parseInt(this.value));
    });

    toggleRowsButton.addEventListener('click', function (event) {
        event.preventDefault();
        const rows = tableBody.querySelectorAll('tr.hidden-row');
        if (rows.length > 0) {
            const newLimit = currentLimit + 10;
            updateVisibleRows(newLimit);
        } else {
            updateVisibleRows(10);
        }
    });

    toggleRowsButton.addEventListener('mouseenter', function () {
        this.style.backgroundColor = '#70999C'; // Set hover background color
        this.style.borderColor = '#1A4B4F'; // Set hover border color
    });

    toggleRowsButton.addEventListener('mouseleave', function () {
        this.style.backgroundColor = '#1E5B5E'; // Set default background color
    });

    resetButton.addEventListener('click', function (event) {
        event.preventDefault();
        searchInput.value = '';
        activeCheckbox.checked = false;
        nonActiveCheckbox.checked = false;
        window.location.href = '/search'; // Reload the page to reset the form and display table_names
    });

    updateVisibleRows(currentLimit);
});
