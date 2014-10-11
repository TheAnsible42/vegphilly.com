var _ = require('lodash'),
    $ = require('jquery'),
    Backbone = require('backbone'),
    google = require('google'),
    map = require('./map');

Backbone.$ = $;

var _vendorMap = map.vendorMap,
    _autoResize = true,
    _defaultCenter = null,
    _vendors = [];

/*global google *, $, _, Backbone */
var SearchFormView = Backbone.View.extend({
    events: {
        "click #clear_all": function (event) {
            this.resetFilters();
            $("#filters").submit();
        },
        "click #clear_search": function (event) {
            $("#search-input").val("");
            $("#filters").submit();
        },
       "change #id_vendors": function (event) {
            var vendor_id = $("#id_vendors").val();
            google.maps.event.trigger(_vendorMap.markers[vendor_id], 'click');
            $('html, body').animate({ scrollTop: 100 }, 'slow');
            $('#map-area').show();
       },
        "change #id_neighborhood, #id_cuisine, #id_checked_features, #id_feature": function (event) {
            $('form#filters').submit();
        }
    },

    initialize: function () {
        //TODO: this is a hack, should be able to fix this in django.
        //TODO: change the feature modelchoicefield to a choicefield
        $("#id_feature").val("");

        _vendorMap.initialize("#map_canvas", _vendors, "summary", _autoResize, _defaultCenter);

        this.styleVegLevelPins();
    },

    styleVegLevelPins: function() {
        var vegLevels = [
            { pinSummary: "Vegan", icon: map.vegCategoryMarkerMapping.vegan },
            { pinSummary: "Vegetarian", icon: map.vegCategoryMarkerMapping.vegetarian },
            { pinSummary: "Non-Vegetarian", icon: map.vegCategoryMarkerMapping.omni }
        ];

        _.each(vegLevels, function (vegLevel) {
            var legendRowTemplate = '<tr><td><img src="<%= icon %>"> <%= pinSummary %></tr></td>',
                tableRow = _.template(legendRowTemplate)({
                    pinSummary: vegLevel.pinSummary,
                    icon: vegLevel.icon
                });

            $("#legend-table tbody").append(tableRow);
        });

        _.each(_.range(0, 7), function (i) {
            var category = map.vegLevelCategoryMapping[i],
                imageUrl = map.vegCategoryMarkerMapping[i];
            $(".veg-level-" + i).attr("src", imageUrl);
        });

    },

    resetFilters: function () {
        $("#id_neighborhood, #id_cuisine, #id_checked_features, #id_feature").val(0);
        $("input:checkbox").val(null);
    }

});

function init(options) {
    _autoResize = options.autoResize;
    _defaultCenter = options.defaultCenter;
    _vendors = options.vendors;

    $(document).ready(function () {
        new SearchFormView({el: $('body') });

        function syncSelect(srcSelector, destSelector) {
            var itemName = $(srcSelector + ' :selected').text();
            $(destSelector).text(itemName);
        }

        var syncNeighborhoodMask = _.partial(syncSelect, '#id_neighborhood', '#neighborhood_mask');
        var syncCuisineMask = _.partial(syncSelect, '#id_cuisine', '#cuisine_mask');

        $('#id_neighborhood').change(syncNeighborhoodMask);
        $('#id_cuisine_tag').change(syncCuisineMask);
        $(document)
            .ready(syncNeighborhoodMask)
            .ready(syncCuisineMask);

        $('#map-show-controls').click(function () {
            $('#map-area').hide();
        });

    });
}

module.exports = {
    init: init
};
