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
document.addEventListener('DOMContentLoaded', function() {
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

  rowLimitSelect.addEventListener('change', function() {
      updateVisibleRows(parseInt(this.value));
  });

  toggleRowsButton.addEventListener('click', function(event) {
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
  toggleRowsButton.addEventListener('mouseenter', function() {
      this.style.backgroundColor = '#70999C';
      this.style.borderColor = '#1A4B4F';
  });

  toggleRowsButton.addEventListener('mouseleave', function() {
      this.style.backgroundColor = '#1E5B5E';
  });

  // Reset search field
  resetButton.addEventListener('click', function(event) {
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

// Enable tooltips
const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]')
const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl))

// P29 score indicator
document.addEventListener('DOMContentLoaded', function() {
  const p29score = parseFloat(document.getElementById('p29result').getAttribute('data-p29result'));
  const radiusp29 = 65;
  const dashArrayp29 = Math.PI * radiusp29 * p29score;

  // Update the dasharray attribute of the score-circle SVG
  const scoreCirclep29 = document.querySelector('.score-circle-p29 svg circle');
  scoreCirclep29.setAttribute('stroke-dasharray', `${dashArrayp29} 10000`);

  // Determine score range and display message
  let message = '';
  if (p29score >= 0 && p29score < 0.2) {
      message = 'Your score is very low.';
  } else if (p29score >= 0.2 && p29score < 0.4) {
      message = 'Your score is low.';
  } else if (p29score >= 0.4 && p29score < 0.6) {
      message = 'Your score is moderate.';
  } else if (p29score >= 0.6 && p29score < 0.8) {
      message = 'Your score is good.';
  } else if (p29score >= 0.8 && p29score <= 1.0) {
      message = 'Your score is excellent!';
  } else {
      message = 'Invalid score range.';
  }

  // Display the message on the page
  const scoreMessageDivp29 = document.getElementById('scoreMessage-p29');
  scoreMessageDivp29.textContent = message;
});




// Min L score indicator
document.addEventListener('DOMContentLoaded', function() {
  const minLScore = parseFloat(document.getElementById('minlresult').getAttribute('data-minl-result'));
  const radiusminl = 65;
  const dashArrayminl = Math.PI * radiusminl * minLScore;

  // Update the dasharray attribute of the score-circle SVG
  const scoreCircleminl = document.querySelector('.score-circle-minl svg circle');
  scoreCircleminl.setAttribute('stroke-dasharray', `${dashArrayminl} 10000`);

  // Determine score range and display message
  let message = '';
  if (minLScore >= 0 && minLScore < 0.2) {
      message = 'Your score is very low.';
  } else if (minLScore >= 0.2 && minLScore < 0.4) {
      message = 'Your score is low.';
  } else if (minLScore >= 0.4 && minLScore < 0.6) {
      message = 'Your score is moderate.';
  } else if (minLScore >= 0.6 && minLScore < 0.8) {
      message = 'Your score is good.';
  } else if (minLScore >= 0.8 && minLScore <= 1.0) {
      message = 'Your score is excellent!';
  } else {
      message = 'Invalid score range.';
  }

  // Display the message on the page
  const scoreMessageDivminl = document.getElementById('scoreMessage-minl');
  scoreMessageDivminl.textContent = message;
});

// Max T score indicator
document.addEventListener('DOMContentLoaded', function() {
  const maxtscoreString = document.getElementById('maxtresult').getAttribute('data-maxt-result');
  const maxtscore = parseFloat(maxtscoreString);
  const radiusmaxt = 65;
  const dashArraymaxt = Math.PI * radiusmaxt * maxtscore;

  // Update the dasharray attribute of the score-circle SVG
  const scoreCirclemaxt = document.querySelector('.score-circle-maxt svg circle');
  scoreCirclemaxt.setAttribute('stroke-dasharray', `${dashArraymaxt} 10000`);

  // Determine score range and display message
  let message = '';
  if (maxtscore >= 0 && maxtscore < 0.2) {
      message = 'Your score is very low.';
  } else if (maxtscore >= 0.2 && maxtscore < 0.4) {
      message = 'Your score is low.';
  } else if (maxtscore >= 0.4 && maxtscore < 0.6) {
      message = 'Your score is moderate.';
  } else if (maxtscore >= 0.6 && maxtscore < 0.8) {
      message = 'Your score is good.';
  } else if (maxtscore >= 0.8 && maxtscore <= 1.0) {
      message = 'Your score is excellent!';
  } else {
      message = 'Invalid score range.';
  }

  // Display the message on the page
  const scoreMessageDivmaxt = document.getElementById('scoreMessage-maxt');
  scoreMessageDivmaxt.textContent = message;
});

// k-anonymity message
document.addEventListener('DOMContentLoaded', function() {
  const k_anonResult = document.getElementById('k_anonresult').getAttribute('data-k-anon-result');
  // Determine score range and display message
  let message = '';
  if (k_anonResult == 0) {
      message = '<placeholder for 0>';
  } else if (k_anonResult > 0 && k_anonResult < 50) {
      message = '<placeholder for 1-50>';
  } else if (k_anonResult >= 50 && k_anonResult < 100) {
      message = '<placeholder 50-100>';
  } else if (k_anonResult > 100) {
      message = '<placeholder > 100>';
  } else {
      message = 'Invalid score range.';
  }

  // Display the message on the page
  const scoreMessageDivkanon = document.getElementById('scoreMessage-kanon');
  scoreMessageDivkanon.textContent = message;
});


// Counting checkboxes and giving messages to user
document.addEventListener('DOMContentLoaded', function() {
  var checkboxes = document.querySelectorAll('input[type="checkbox"][name="columns_to_drop"]');
  var countDisplay = document.getElementById('selected-count');
  var messageDisplay = document.getElementById('selection-message');


  function updateSelectedCount() {
      var selectedCount = 0;
      checkboxes.forEach(function(checkbox) {
          if (checkbox.checked) {
              selectedCount++;
          }
      });
      countDisplay.textContent = selectedCount + ' checkboxes selected';


      // Conditional message based on selected count
      if (selectedCount === 0) {
          messageDisplay.textContent = 'Do you want to continue? You have no checkboxes selected.';
      } else if (selectedCount === 1) {
          messageDisplay.textContent = 'Do you want to remove ' + selectedCount + ' column? This action cannot be undone.';
      } else {
          messageDisplay.textContent = 'Do you want to remove ' + selectedCount + ' columns? This action cannot be undone.';
      }
  }

  checkboxes.forEach(function(checkbox) {
      checkbox.addEventListener('change', updateSelectedCount);
  });

  // Initial count display
  updateSelectedCount();
});

document.addEventListener('DOMContentLoaded', function() {
  var checkboxes = document.querySelectorAll('input[type="checkbox"][name="columns_to_drop"]');
  var countDisplay = document.getElementById('selected-count');
  var messageDisplay = document.getElementById('selection-message');


  function updateSelectedCount() {
      var selectedCount = 0;
      checkboxes.forEach(function(checkbox) {
          if (checkbox.checked) {
              selectedCount++;
          }
      });
      countDisplay.textContent = selectedCount + ' checkboxes selected';


      // Conditional message based on selected count
      if (selectedCount === 0) {
          messageDisplay.textContent = 'Do you want to continue? You have no checkboxes selected.';
      } else if (selectedCount === 1) {
          messageDisplay.textContent = 'Do you want to remove ' + selectedCount + ' column? This action cannot be undone.';
      } else {
          messageDisplay.textContent = 'Do you want to remove ' + selectedCount + ' columns? This action cannot be undone.';
      }
  }

  checkboxes.forEach(function(checkbox) {
      checkbox.addEventListener('change', updateSelectedCount);
  });

  // Initial count display
  updateSelectedCount();
});