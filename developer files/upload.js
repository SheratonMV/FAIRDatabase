$(document).ready(function() {
    $('form').submit(function(event) {
        event.preventDefault();

        var formData = new FormData($(this)[0]);
        var progressBar = $('#progress-bar');
        var progressLabel = $('#progress-label');

        $.ajax({
            url: '/upload',
            type: 'POST',
            data: formData,
            cache: false,
            contentType: false,
            processData: false,
            xhr: function() {
                var xhr = new window.XMLHttpRequest();
                xhr.upload.addEventListener('progress', function(event) {
                    if (event.lengthComputable) {
                        var percentComplete = Math.round((event.loaded / event.total) * 100);
                        progressBar.val(percentComplete);
                        progressLabel.text(percentComplete + '%');
                    }
                }, false);
                return xhr;
            },
            success: function(response) {
                // Handle the success response
                console.log(response);
            },
            error: function(xhr, status, error) {
                // Handle the error response
                console.log(error);
            }
        });
    });
});
