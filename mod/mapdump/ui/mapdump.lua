-- MapDump's own UI context: Ctrl+Shift+D copies the dump to the clipboard.
include("mapdump_core")

local function OnInput(input)
	if input:GetMessageType() == KeyEvents.KeyUp
		and input:GetKey() == Keys.D
		and input:IsShiftDown()
		and input:IsControlDown() then
		MapDump_SafeDump(true)
		return true
	end
	return false
end

ContextPtr:SetInputHandler(OnInput, true)
Events.LoadScreenClose.Add(function() MapDump_SafeDump(false) end)
Events.LocalPlayerTurnBegin.Add(function() MapDump_SafeDump(false) end)
pcall(function() Controls.Status:SetText("[MapDump] loaded") end)
print("MAPDUMP|LOADED")
