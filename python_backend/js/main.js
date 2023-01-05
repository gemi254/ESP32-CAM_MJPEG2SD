var conn;
const host = window.location.host
const ctrlUrl = 'ws://'+host+'/wsc';
var connDevices={};
var availableTags = [];

$(document).ready(function(e){
	conn = new WebSocket(ctrlUrl);
	if( window["WebSocket"] && conn ) {
		
		conn.onopen = function (evt) {            
            console.log("Opened: " + ctrlUrl)	
        };

        conn.onclose = function (evt) {
			console.log("Closed: " + ctrlUrl)    
        };
        
		conn.onmessage = function (evt) {			
			var message = evt.data;
			try {
			    var json = JSON.parse(evt.data);
				id = json['self.id']
				msg = json['msg']
				pushLog(id," < "+msg)
				if(msg=="info"){
					var ojson = JSON.parse($('#info_'+id).val())
					var njson = Object.assign({}, ojson, json)					
					$('#info_'+id).val(JSON.stringify(njson))
					$('#vid_'+id).prop('title',pretyJson(njson))
				}else if(msg.startsWith("framesize")){
					m = msg.split("=")
					val =parseInt(m[1])
					const ctrl = '#framesize_'+id;
					$(ctrl).val(val) 					
				}else{ //Update info
					try{
						m = msg.split("=")
						var ojson = JSON.parse($('#info_'+id).val())
						ojson[m[0]]=m[1]
						$('#info_'+id).val(JSON.stringify(ojson))
						$('#vid_'+id).prop('title',pretyJson(ojson))
		
					}catch(e){
						console.log('Error:',e.message)
					}
				}
								
			} catch (e) {
			    json=null;
			 }			
		}	
	}else{
		const msg = "<b>Your browser does not support WebSockets.</b>";
		console.log(msg)
	}
	
	$('#btEdit').click(function(e){		
		$('#btSave').show();
		$('#btEdit').hide()
		$('#presets_edit').show()
		$('.presets_ctrl').hide()
	})
	
	$('#btSave').click(function(e){		
		var data = new FormData();
		var presets = $('#presets').val();
		presets.replaceAll('\r','')
		data.append('presets', presets );
		var xhr = new XMLHttpRequest();
		xhr.open('POST', '/control', true);
		xhr.send(data);
		
		$('#btEdit').show();
		$('#btSave').hide()
		$('#presets_edit').hide()
		$('.presets_ctrl').show()
		loadPresets()
	})
	
	loadPresets()
		
	$('[id^="info_"]').each(function() {
		id = this.id.replace('info_','')
	 	var j = $.parseJSON(this.value)
		const ctrl = '#framesize_'+id;
		$(ctrl).val( parseInt(j.framesize) ) 
		$('#vid_'+id).prop('title',pretyJson(j))
		
		connDevices[id]={ log: [] };
		
		if(availableTags.length==0){
			for (var key in j) {
				if(!readOnlyTagsCmds.includes(key)){
					availableTags.push(key);
				}
			};
			availableTags = availableTags.concat( additionalTagsCmds )
		
			$('#cmdAll').autocomplete({			 
				source: availableTags,
				/*appendTo: jQuery('.suggestions')*/	  	
			});
		}			
		
		$('#cmd_'+id).autocomplete({							 
			source: availableTags,
		});
		
	})
	
	window.setInterval(refresh ,60000)
	
	$('#cmdAll').keypress(function(e){
		if(e.which == 13) {	
			for( const id in connDevices){
				sendCommand(id,this.value + '')
			}			
		}
	})
	$('#presetsAll').change(function(e){
		$('#cmdAll').val( this[this.selectedIndex].value )
	})
	
	$('#btSend').click(function(e){
		cmd = $('#cmdAll').val()
		if(!cmd) return; 
		for( const id in connDevices){
			sendCommand(id, cmd+ '')
		}
	})		
	
	$('[id^="cmd_"]').mouseover(function(e){
		id = e.currentTarget.id.replace('cmd_','')
		const log = connDevices[id]['log']
		var ll = ""
		for(const l in log){
			ll +=log[l]+'\n'
		}
		$('#cmd_'+id).prop('title',ll)
	})

	$('[id^="cmd_"]').keypress(function(e){
		if(e.which == 13) {
			id = e.currentTarget.id.replace('cmd_','')
			sendCommand(id,this.value + '');
		}
	})
	
	$('[id^="framesize_"]').change(function(e){
		id = e.currentTarget.id.replace('framesize_','')
		sendCommand(id,'framesize=' + this[this.selectedIndex].value);
	})
	$('[id^="pause_"]').click(function(e){
		id = e.currentTarget.id.replace('pause_','')
		if(this.value=="Pause"){
			sendCommand(id,'pause=1');
			this.value= 'Paused'	
			this.setAttribute('style', 'color: red');
		}else{
			sendCommand(id,'pause=0');
			this.value= 'Pause'
			this.setAttribute('style', 'color: black');
		}
		
	})
		
	function sendCommand(id, cmd){
		pushLog(id," > "+ cmd)
		var j = {}
		j['id']=id
		j['cmd']=cmd
		conn.send(JSON.stringify(j) )
	}
	
	function refresh(){
		for( const id in connDevices){
			sendCommand(id,"status?q")
		}
	}	
});

function pretyJson(json){
	var s =''
	for (var key in json) {
		if(displayTags.includes(key)) s += key + ": " +json[key] + "\n"
	};
	return s;
}
function pushLog(id, msg){

	if(connDevices[id]['log'].length >30){
		connDevices[id]['log'].shift()	
	}	
	var tm = (new Date()).toISOString().split('T')[0] +" "+ (new Date()).toLocaleTimeString().split(" ")[0]
	console.log(tm+" "+ id + ""+msg)	 
	msg = tm + " " + msg
	connDevices[id]['log'].push(msg);
}				
function loadPresets()
{
	$.get("/templates/presets.txt?"+(new Date()).getTime(), function(data){		
		lines = data.split('\n')
		$('#presetsAll').empty()
		$('#presetsAll').append('<option value="">-- Please select --</option>')
		for(var k in lines){
			lines[k] = lines[k].replaceAll('\r','')
			items = lines[k].split("|")
			if(items.length<2) continue
			var opt ='<option value="' + items[1].trim() + '">' + items[0].trim() + '</option>'
			$('#presetsAll').append(opt)
		}
		$('#presets').val(data.replaceAll('\r',''));
	})
}
var displayTags = [
"fps",
"framesize",
"clock",
"forceRecord",
"free_heap",
"used_bytes",
"free_bytes",
"up_time",
"wifi_rssi",
"motion",
"quality",
"night",
"record",
"autoUpload",
"atemp",
"local_ip",
"fw_version"
]

var additionalTagsCmds = [
"save",
"reset",
"socketFps",
"dbgMotion",
"dbgVerbose",
"delete",
"upload",
"stopStream",
"lamp",
"pause",
"resetLog"
]
var readOnlyTagsCmds = [
"wifi_rssi",
"free_psram",
"free_heap",
"up_time",
"total_bytes",
"free_bytes",
"used_bytes",
"card_size", 
"clockUTC", 
"clock", 
"battv", 
"atemp", 
"night",
"timestamp",
"self.id",
"fw_version",
"msg", 
"llevel" 
];
