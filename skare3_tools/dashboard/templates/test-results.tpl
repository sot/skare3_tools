<!DOCTYPE html>
<html>
<head>
    <title>Ska Packages</title>
    <script src="https://ajax.googleapis.com/ajax/libs/jquery/1.11.2/jquery.js" type="text/javascript"></script>
    <script src="https://netdna.bootstrapcdn.com/bootstrap/3.3.1/js/bootstrap.min.js" type="text/javascript"></script>
    <script src="watable/jquery.watable.js" type="text/javascript" charset="utf-8"></script>
    <link rel='stylesheet' href="https://netdna.bootstrapcdn.com/bootstrap/3.3.1/css/bootstrap.min.css" />
    <link rel='stylesheet' href='watable/watable.css'/>
    <style type="text/css">
        body { padding: 30px; font-size: 12px }
    </style>
</head>
<body>
    <h2>Skare3 Tests</h2>
    <p>
    Directory: {{ results.log_directory }} </br>
    </p>

    <div id="ska_packages_table" style="width:auto"></div>

    <script type="text/javascript">
        $(document).ready( function() {
          var waTable = $('#ska_packages_table').WATable({
            data: getData(),
            debug:false,                //Prints some debug info to console
            dataBind: false,             //Auto-updates table when changing data row values. See example below. (Note. You need a column with the 'unique' property)
            pageSize: 1000,                //Initial pagesize
            pageSizePadding: false,      //Pads with empty rows when pagesize is not met
            //transition: 'slide',       //Type of transition when paging (bounce, fade, flip, rotate, scroll, slide).Requires https://github.com/daneden/animate.css.
            //transitionDuration: 0.2,    //Duration of transition in seconds.
            //filter: true,               //Show filter fields
            sorting: true,              //Enable sorting
            sortEmptyLast:false,         //Empty values will be shown last
            columnPicker: false,         //Show the columnPicker button
            pageSizes: [1,5,8,12,200],  //Set custom pageSizes. Leave empty array to hide button.
            hidePagerOnEmpty: true,     //Removes the pager if data is empty.
            checkboxes: false,           //Make rows checkable. (Note. You need a column with the 'unique' property)
            checkAllToggle:true,        //Show the check-all toggle
            preFill: false,              //Initially fills the table with empty rows (as many as the pagesize).
            types: {                    //If you want, you can supply some properties that will be applied for specific data types.
              string: {
                //filterTooltip: "Giggedi...",    //What to say in tooltip when hoovering filter fields. Set false to remove.
                placeHolder: "Type here..."    //What to say in placeholder filter fields. Set false for empty.
              },
              number: {
                decimals: 1   //Sets decimal precision for float types
              },
              bool: {
                //filterTooltip: false
              },
              date: {
                utc: true,            //Show time as universal time, ie without timezones.
                //format: 'yyyy-MM-dd hh:mm:ss',   //The format. See all possible formats here http://arshaw.com/xdate/#Formatting.
                format: 'MMM dd yyyy, hh:mm:ss',   //The format. See all possible formats here http://arshaw.com/xdate/#Formatting.
                datePicker: true      //Requires "Datepicker for Bootstrap" plugin (http://www.eyecon.ro/bootstrap-datepicker).
              }
            },
            tableCreated: function (data) {
              $('tfoot p, tfoot .pagesize, tfoot .pagelinks', this).hide();
              //$('tfoot p, li:not(:first):not(:last)', this).hide();
            }
          }).data('WATable');  //This step reaches into the html data property to get the actual WATable object. Important if you want a reference to it as we want here.
        });


        function getStatusClass(value) {
	if (value == "FAIL") {
        return "red";
	}
	return "green";
	};

        function getData() {

          var cols = {
            pkg: {
              index: 1,
              type: "string",
              friendly: "Package",
              placeHolder: "pkg name", // place holder in the filter entry
              //filter: false, // would remove filtering
              sortOrder: "asc", //Data will initially be sorted by this column. Possible are "asc" or "desc"
              //format: "<a href='https://github.com/sot/{0}'>{0}</a>",
            },
            test: {
              index: 2,
              type: "string",
              friendly: "Test"
            },
            status: {
              index: 3,
              type: "string",
              friendly: "Status",
              format: "{0}</a>",
            }
          };

	  {% set i = 0 %}
          var rows = [
            {% for pkg, result in results.results.items() %}
	        {% for name, test_result in result.tests.items() %}
                    {% set i = i + 1 %}
            { i: "{{ i }}",
              pkg: "{{ pkg }}",
              test: "{{ name }}",
	      status: "{{ test_result }}",
              statusCls: getStatusClass("{{ test_result }}"),
              statusFormat: "<a href='https://icxc.cfa.harvard.edu/aspect/skare3/testr/logs/{{
          results.log_directory }}/{{ pkg }}/{{ name }}.log'> {{ test_result }} </a>",
            },
                {% endfor %}
            {% endfor %}
          ];

          var data = {
            cols: cols,
            rows: rows,
            extra: {} // optional
            };
          return data;
        }

</script>
</body>
</html>
