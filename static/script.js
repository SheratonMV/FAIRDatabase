// Sidebar state storage
document.addEventListener("DOMContentLoaded", function() {
    const isCollapsed = localStorage.getItem("sidebarCollapsed") === "true";
    const body = document.getElementById("body");
    const sidebar = document.getElementById("sidebar");
    const pageContent = document.getElementById("page-content");
    const collapseIcon = document.getElementById("collapseIcon");
    const profilePic = document.getElementById("profilePic");
    const name = document.getElementById("profileName");

    if (isCollapsed) {
        body.classList.add("collapsed");
        sidebar.style.width = "70px";
        pageContent.style.marginLeft = "70px";
        collapseIcon.classList.remove("fa-chevron-left");
        collapseIcon.classList.add("fa-chevron-right");
        profilePic.style.width = "35px";
        profilePic.style.height = "35px"; 
        name.style.display = "none"; 
    }
});

// Toggling of the sidebar
function toggleSidebar() {
    const body = document.getElementById("body");
    const sidebar = document.getElementById("sidebar");
    const pageContent = document.getElementById("page-content");
    const collapseIcon = document.getElementById("collapseIcon");
    const profilePic = document.getElementById("profilePic");
    const name = document.getElementById("profileName");
    const isCollapsed = body.classList.contains("collapsed");

    body.classList.toggle("collapsed");
    localStorage.setItem("sidebarCollapsed", !isCollapsed);

    if (!isCollapsed) {
        sidebar.style.width = "70px";
        pageContent.style.marginLeft = "70px";
        collapseIcon.classList.remove("fa-chevron-left");
        collapseIcon.classList.add("fa-chevron-right");
        profilePic.style.width = "35px"; 
        profilePic.style.height = "35px";
        name.style.display = "none"; 
    } else {
        sidebar.style.width = "250px";
        pageContent.style.marginLeft = "250px";
        collapseIcon.classList.remove("fa-chevron-right");
        collapseIcon.classList.add("fa-chevron-left");
        profilePic.style.width = "80px"; 
        profilePic.style.height = "80px"; 
        name.style.display = "block";
    }
}

// For Bootstrap alerts
document.addEventListener('DOMContentLoaded', () => {
    $('.alert').alert()
});

// Load more function for search
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

    // Bugfix for button color not working
    toggleRowsButton.addEventListener('mouseenter', function () {
        this.style.backgroundColor = '#70999C'; 
        this.style.borderColor = '#1A4B4F'; 
    });

    toggleRowsButton.addEventListener('mouseleave', function () {
        this.style.backgroundColor = '#1E5B5E'; 
    });

    // Reset search field
    resetButton.addEventListener('click', function (event) {
        event.preventDefault();
        searchInput.value = '';
        activeCheckbox.checked = false;
        nonActiveCheckbox.checked = false;
        window.location.href = '/search'; 
    });

    updateVisibleRows(currentLimit);
});

// Validate form upload
function validateForm() {
    var reference = document.getElementById("reference").value;
    var description = document.getElementById("description").value;
    var relational = document.getElementById("relational").value;
    var fileInput = document.getElementById("file-input");
    
    var filePath = fileInput.value;
    var allowedExtensions = /(\.csv)$/i;

    if (reference === "") {
      $('#reference-error').show();
      return false;
    } else {
      $('#reference-error').hide();
    }

    if (description === "") {
      $('#description-error').show();
      return false;
    } else {
      $('#description-error').hide();
    }
    if (relational === "") {
      $('#relational-error').show();
      return false;
    } else {
      $('#relational-error').hide();
    }

    if (!filePath) {
      $('#file-error').show();
      return false;
    } else {
      $('#file-error').hide();
    }

    if (!allowedExtensions.exec(filePath)) {
      alert("Please upload a file having extensions .csv only.");
      fileInput.value = '';
      return false;
    }

    $('#uploadModal').modal('show');
    return true;
  }

// Close form and upload
  function uploadAndCloseForm() {
  var formData = new FormData($("#upload-form")[0]);
  
  $.ajax({
    url: '/upload',
    type: 'POST',
    data: formData,
    processData: false,
    contentType: false,
    xhr: function() {
      var xhr = new window.XMLHttpRequest();
      xhr.upload.addEventListener("progress", function(evt) {
        if (evt.lengthComputable) {
          var progress = Math.round((evt.loaded / evt.total) * 100);
          $("#progress").css("width", progress + "%");
          $("#progress-message").text("Creating table:" + progress + "% . Waiting to finalize...");
        }
      }, false);
      return xhr;
    },
    success: function(response) {
      $("#progress-message").text("File uploaded successfully.");
    },
    error: function(error) {
      $("#progress-message").text("Error uploading file.");
    }
  });
}

$(document).ready(function() {
  $("#upload-form").submit(function(e) {
    e.preventDefault();
    uploadAndCloseForm();
  });
});

// Close upload form
function closeUploadForm() {
    $('#uploadModal').modal('hide');
}
  

// Validate update form
function validateUpdateForm() {
  var row_id = document.getElementById("row_id").value;
  var column_name = document.getElementById("column_name").value;
  var new_value = document.getElementById("new_value").value;
  

  if (row_id === "") {
    $('#row_id-error').show();
    return false;
  } else {
    $('#row_id-error').hide();
  }

  if (column_name === "") {
    $('#column_name-error').show();
    return false;
  } else {
    $('#column_name-error').hide();
  }

  if (new_value === "") {
    $('#new_value-error').show();
    return false;
  } else {
    $('#new_value-error').hide();
  }

  $('#updateModal').modal('show');
  return true;
}

// Close update form
function closeUpdateForm() {
  $('#updateModal').modal('hide');
}

// Close search form
function closeSearchForm() {
  $('#searchModal').modal('hide');
}

// Open search form
function openSearchForm() {
  $('#searchModal').modal('show');
}

// Close search form with delay
function downloadAndCloseSearchForm() {
  $('#searchModal').modal('show');
  
  setTimeout(function() {
    $('#searchModal').modal('hide');
  }, 200); 
}

// Set focus search bar shortcut


// Enable tooltips
const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]')
const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl))