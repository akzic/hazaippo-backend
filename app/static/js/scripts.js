function initMap(mapElementId) {
    var map = new google.maps.Map(document.getElementById(mapElementId), {
        center: { lat: 35.1815, lng: 136.9066 }, // 名古屋市の中心座標
        zoom: 12
    });

    var service = new google.maps.places.PlacesService(map);

    var materialsForm = document.getElementById('materialsSearchForm');
    if (materialsForm) {
        materialsForm.addEventListener('submit', function(e) {
            e.preventDefault();
            var radius = document.getElementById('radius').value * 1000; // kmをmに変換
            if (!radius) {
                alert('検索範囲（半径km）を入力してください。');
                return;
            }
            var center = map.getCenter();

            var request = {
                location: center,
                radius: radius,
                type: ['store'] // 検索する場所の種類
            };

            service.nearbySearch(request, function(results, status) {
                if (status === google.maps.places.PlacesServiceStatus.OK) {
                    for (var i = 0; i < results.length; i++) {
                        var place = results[i];
                        new google.maps.Marker({
                            position: place.geometry.location,
                            map: map,
                            title: place.name
                        });
                    }
                }
            });
        });
    }

    var wantedForm = document.getElementById('wantedMaterialsSearchForm');
    if (wantedForm) {
        wantedForm.addEventListener('submit', function(e) {
            e.preventDefault();
            var radius = document.getElementById('wanted_radius').value * 1000; // kmをmに変換
            if (!radius) {
                alert('検索範囲（半径km）を入力してください。');
                return;
            }
            var center = map.getCenter();

            var request = {
                location: center,
                radius: radius,
                type: ['store'] // 検索する場所の種類
            };

            service.nearbySearch(request, function(results, status) {
                if (status === google.maps.places.PlacesServiceStatus.OK) {
                    for (var i = 0; i < results.length; i++) {
                        var place = results[i];
                        new google.maps.Marker({
                            position: place.geometry.location,
                            map: map,
                            title: place.name
                        });
                    }
                }
            });
        });
    }
}

document.addEventListener("DOMContentLoaded", function() {
    var imageInput = document.getElementById("image");
    var imagePreview = document.getElementById("imagePreview");

    if (imageInput) {
        imageInput.addEventListener("change", function() {
            var file = this.files[0];
            if (file) {
                var reader = new FileReader();
                reader.onload = function(e) {
                    imagePreview.src = e.target.result;
                    imagePreview.style.display = "block";
                };
                reader.readAsDataURL(file);
            }
        });
    }

    var materialType = document.getElementById('material_type');
    if (materialType) {
        materialType.addEventListener('change', function() {
            var woodSubtypeDiv = document.getElementById('_div');
            var finishTypeDiv = document.getElementById('finish_type_div');
            if (woodSubtypeDiv) {
                woodSubtypeDiv.style.display = this.value === '木材' ? 'block' : 'none';
            }
            if (finishTypeDiv) {
                finishTypeDiv.style.display = 'none';
            }
        });
    }

    var woodSubtype = document.getElementById('');
    if (woodSubtype) {
        woodSubtype.addEventListener('change', function() {
            var finishTypeDiv = document.getElementById('finish_type_div');
            if (finishTypeDiv) {
                finishTypeDiv.style.display = this.value === '仕上げ材' ? 'block' : 'none';
            }
        });
    }

    var imageInput = document.getElementById('image');
    if (imageInput) {
        imageInput.addEventListener('change', function() {
            var file = this.files[0];
            if (file) {
                var reader = new FileReader();
                reader.onload = function(e) {
                    document.getElementById('imagePreview').src = e.target.result;
                    document.getElementById('imagePreview').style.display = 'block';
                };
                reader.readAsDataURL(file);
            }
        });
    }

    $('#location').on('input', function() {
        if ($(this).val()) {
            $('#radius').val('');
            $('#map-container').hide();
        }
    });

    $('#radius').on('input', function() {
        if ($(this).val()) {
            $('#location').val('');
            $('#map-container').show();
        } else {
            $('#map-container').hide();
        }
    });

    $('#wanted_location').on('input', function() {
        if ($(this).val()) {
            $('#wanted_radius').val('');
            $('#map-wanted-container').hide();
        }
    });

    $('#wanted_radius').on('input', function() {
        if ($(this).val()) {
            $('#wanted_location').val('');
            $('#map-wanted-container').show();
        } else {
            $('#map-wanted-container').hide();
        }
    });
});

function openTab(evt, tabName) {
    var i, tabcontent, tabbuttons;
    tabcontent = document.getElementsByClassName("tab-content");
    for (i = 0; i < tabcontent.length; i++) {
        tabcontent[i].style.display = "none";
    }
    tabbuttons = document.getElementsByClassName("tab-button");
    for (i = 0; i < tabbuttons.length; i++) {
        tabbuttons[i].className = tabbuttons[i].className.replace(" active", "");
    }
    document.getElementById(tabName).style.display = "block";
    evt.currentTarget.className += " active";
}

window.addEventListener('load', function() {
    initMap('map-materials');
    initMap('map-wanted-materials');
});
