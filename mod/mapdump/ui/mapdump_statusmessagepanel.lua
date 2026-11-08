-- Hook: replaces StatusMessagePanel's script with the original plus MapDump,
-- because MapDump's own context does not load on the Linux port.
-- On load: planned map tacks are placed and the map is dumped. Each turn: the map is dumped.
-- Ctrl+Shift+T: place the planned tacks now, with the result shown as a status message.
-- The panel only sets its own input handler in its debug test mode, so taking it is safe.
pcall(function() GameConfiguration.SetValue("MAPDUMP_HOOK", "MAPDUMP|STATUS|msg=statusmessagepanel hook started\n") end)
include("statusmessagepanel")
include("mapdump_core")

local function Notify(text)
	pcall(function() OnStatusMessage("Map Dump: " .. text, 6, ReportingStatusTypes.DEFAULT) end)
end

local function OnInput(input)
	if input:GetMessageType() == KeyEvents.KeyUp
		and input:GetKey() == Keys.T
		and input:IsShiftDown()
		and input:IsControlDown() then
		Notify("tacks " .. tostring(MapDump_SafePlaceTacks()))
		return true
	end
	return false
end

ContextPtr:SetInputHandler(OnInput, true)
Events.LoadScreenClose.Add(function()
	MapDump_SafePlaceTacks()
	MapDump_SafeDump(true)
end)
Events.LocalPlayerTurnBegin.Add(function() MapDump_SafeDump(true) end)
print("MAPDUMP|LOADED_IN_STATUSMESSAGEPANEL")
