$(function($) {
    $.cardstories_stats = {
        data: null,
            
        init: function() {
            var $this = this;
            var deferred = $.Deferred();

            $.when($this.load_data()).done(function() {
                $this.show_stats();
                deferred.resolve();
            })
            
            return deferred.promise();
        },
        
        load_data: function() {
            var $this = this;
            var deferred = $.Deferred();
            
            $.getJSON("data/cardstories_stats.json", function(data) {
                $this.data = data;
                
                // Hard-code color indices to prevent them from shifting as sets are turned on/off
                $.each($this.data, function(i, dataset) {
                    $.each(dataset, function(j, row) {
                        row.color = j*2;
                        i++;
                    });
                });

                deferred.resolve();
            });
            
            return deferred.promise();
        },
        
        show_stats: function() {
            var $this = this;
            
            // Concurrent players //
            
            $this.show_stats_for('concurrent_players', {
                show: false,
                unit: '',
                default_selector: function(label) {
                    return true;
                },
            }, {
                yaxis: { min: 0, tickDecimals: 0 },
                xaxis: { mode: "time" },
                lines: { show: true, fill: true, steps: true },
                crosshair: { mode: "x" },
                grid: { hoverable: true, autoHighlight: false },
                selection: { mode: "x" },
            });
            
            // Player activity //
            
            $this.show_stats_for('active_players_per_week', {
                show: true,
                header: false,
                unit: '',
                default_selector: function(label) {
                    if(label !== "New players") {
                        return true;
                    } else {
                        return false;
                    }
                },
            }, {
                yaxis: { min: 0, tickDecimals: 0 },
                xaxis: { mode: "time", tickSize: [ 7, "day" ] },
                lines: { show: true, fill: true, steps: true },
                crosshair: { mode: "x" },
                grid: { hoverable: true, autoHighlight: false },
            });
            
            // Funnel //
            
            $this.show_stats_for('funnel', {
                show: true,
                header: true,
                unit: '%',
                default_selector: function(label) {
                    if(label === "Average") {
                        return true;
                    } else {
                        return false;
                    }
                }
            }, {
                yaxis: { min: 0, tickDecimals: 0 },
                xaxis: { tickDecimals: 0 },
                crosshair: { mode: "x" },
                lines: { fill: true, steps: true },
                grid: { hoverable: true, autoHighlight: false },
            });
            
            // Cohorts //
            
            $this.show_stats_for('weekly_actives_percent', {
                show: true,
                header: true,
                unit: '%',
                default_selector: function(label) {
                    if(label === "Average") {
                        return true;
                    } else {
                        return false;
                    }
                }
            }, {
                yaxis: { min: 0, tickDecimals: 0 },
                xaxis: { tickDecimals: 0 },
                crosshair: { mode: "x" },
                lines: { fill: true },
                grid: { hoverable: true, autoHighlight: false },
            });
            
            // Enough players? //
            
            $this.show_stats_for('enough_players_percent', {
                show: false,
                unit: '%',
                default_selector: function(label) {
                    return true;
                },
            }, {
                yaxis: { min: 0, max: 100, tickDecimals: 0 },
                xaxis: { mode: "time" },
                lines: { show: true, fill: true, steps: true },
                crosshair: { mode: "x" },
                grid: { hoverable: true, autoHighlight: false },
                selection: { mode: "x" },
            });            
        },
        
        show_stats_for: function(dataset_name, table_options, plot_options) {
            var $this = this;
            var table = $('#table_'+dataset_name);
 
            if(table_options.show) {
                $this.draw_table(dataset_name, table_options, plot_options);                
                $this.plot_according_to_choices(dataset_name, plot_options);
            } else {
                $this.draw_plot(dataset_name, plot_options, $this.data[dataset_name]);
            }
        },

        draw_table: function(dataset_name, table_options, plot_options) {
            var $this = this;
            var dataset = $this.data[dataset_name];
            var table = $('#table_'+dataset_name);
            
            // Table - Header
            $.each(dataset[0].data, function(i, value) {
                var header = '';
                if(table_options.header === true) {
                    header = value[0];
                } 
                $('thead tr', table).append('<th>'+header+'</th>');
            });
            
            // Table - Body
            $.each(dataset, function(i, row) {
                var checked = '';
                
                if (table_options.default_selector(row.label)) {
                    checked = 'checked="checked"';
                }
                toggle = '<input type="checkbox" name="' + row.label +
                                       '" '+checked+' "id="id' + row.label + '">' +
                                       '<label for="id' + row.label + '">'
                                        + row.label + '</label>';
                
                var line = '<tr><td>'+toggle+'</td>';
                
                $.each(row.data, function(j, point) {
                    line += '<td>'+point[1]+table_options.unit+'</td>';
                });
                line += '</tr>';
                $('tbody', table).append($(line));
            });
            
            // Table
            $("#table_"+dataset_name).tablesorter();
            
            // Activation/deactivation of individual plot lines
            $("input", table).click(function() {
                $this.plot_according_to_choices(dataset_name, plot_options);
            });            
        },
        
        plot_according_to_choices: function(dataset_name, plot_options) {
            var $this = this;
            var data = [];
            var table = $('#table_'+dataset_name);
            var dataset = $this.data[dataset_name];
            var plot = null;

            $("input:checked", table).each(function () {
                var key = $(this).attr("name");
                if (key) {
                    $.each(dataset, function() {
                        if(this.label === key) {
                            data.push(this);
                        }
                    })
                }
            });
            
            $this.draw_plot(dataset_name, plot_options, data);
        },
        
        draw_plot: function(dataset_name, plot_options, data) {
            var $this = this;
            var orig_xaxis = plot_options.xaxis;
            
            if (data.length > 0) {
                var plot = $.plot($("#plot_"+dataset_name), data, plot_options);
            }
            
            // Values in legend
            $("#plot_"+dataset_name).unbind("plothover");
            $("#plot_"+dataset_name).bind("plothover", function(event, pos, item) {
                $this.update_plot_legend(dataset_name, plot, pos);
            });
            
            // Selection zoom
            $("#plot_"+dataset_name).bind("plotselected", function (event, ranges) {
                // do the zooming
                plot = $.plot($("#plot_"+dataset_name), data,
                              $.extend(true, {}, plot_options, {
                                  xaxis: { min: ranges.xaxis.from, max: ranges.xaxis.to }
                              }));
            });
            $("#reset_"+dataset_name).click(function () {
                $.plot($("#plot_"+dataset_name), data, 
                                  $.extend(true, {}, plot_options, {
                                          xaxis: orig_xaxis }));
            });
        },
        
        update_plot_legend: function(dataset_name, plot, pos) {
            var legends = $("#plot_"+dataset_name+" .legendLabel");
            var axes = plot.getAxes();
            if (pos.x < axes.xaxis.min || pos.x > axes.xaxis.max ||
                pos.y < axes.yaxis.min || pos.y > axes.yaxis.max)
                return;

            var i, j, dataset = plot.getData();
            for (i = 0; i < dataset.length; ++i) {
                var series = dataset[i];

                // find the nearest points, x-wise
                for (j = 0; j < series.data.length; ++j)
                    if (series.data[j][0] > pos.x)
                        break;

                y = series.data[j-1][1];
                
                legends.eq(i).text(series.label + " = " + Math.round(y.toFixed(2)));
            }
        },
    };
    
    $.cardstories_stats.init();

});
