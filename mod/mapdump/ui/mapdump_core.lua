-- MapDump: dumps every tile revealed to the local player.
-- Runs in the InGame UI context (Game.GetLocalPlayer and PlayersVisibility exist here).
-- The game's Lua has no io library; the dump goes to the clipboard (Ctrl+Shift+D)
-- and to print(), which reaches Lua.log only on builds that write one.
-- Output format, one record per line, fields as key=value separated by '|':
--   MAPDUMP|BEGIN|id=..|turn=..|player=..|w=..|h=..
--   MAPDUMP|TILE|i=..|x=..|y=..|terrain=..|...
--   MAPDUMP|CITY|id=..|name=..|x=..|y=..|pop=..
--   MAPDUMP|END|id=..|tiles=..

local PREFIX = "MAPDUMP|"
local dumpCount = 0

-- Stores a value in the game configuration, which is written into every save
-- (including autosaves), so it can be read from outside the game.
function MapDump_SetConfig(key, value)
	local ok, err = pcall(function() GameConfiguration.SetValue(key, value) end)
	return ok, err
end

-- Load marker, set before anything else can fail, so the save shows whether this script runs.
MapDump_SetConfig("MAPDUMP_STATUS", PREFIX .. "STATUS|msg=core loaded\n")
pcall(function() UIManager:SetClipboardString(PREFIX .. "LOADED") end)

-- Calls a plot method by name, returning nil if it is missing or errors,
-- so one API difference between game versions does not abort the dump.
local function Call(obj, method, ...)
	local fn = obj[method]
	if fn == nil then return nil end
	local ok, result = pcall(fn, obj, ...)
	if ok then return result end
	return nil
end

local function TypeName(tbl, index, field)
	if index == nil or index < 0 then return "NONE" end
	local row = tbl[index]
	if row == nil then return "NONE" end
	return row[field] or "NONE"
end

local function Bool(v)
	if v then return "1" end
	return "0"
end

-- Lines of the dump being built; DumpMap returns them so callers can print or copy them.
local lines = {}

local function Emit(kind, fields)
	table.insert(lines, PREFIX .. kind .. "|" .. table.concat(fields, "|"))
end

local function SetStatus(text)
	pcall(function() Controls.Status:SetText("[MapDump] " .. text) end)
end

local function DumpMap()
	lines = {}
	local playerID = Game.GetLocalPlayer()
	if playerID == nil or playerID < 0 then return nil end

	local vis = PlayersVisibility[playerID]
	local player = Players[playerID]
	if vis == nil or player == nil then return nil end
	local playerResources = player:GetResources()

	local yields = {}
	for row in GameInfo.Yields() do
		table.insert(yields, { index = row.Index, name = row.YieldType })
	end

	dumpCount = dumpCount + 1
	local dumpID = tostring(Game.GetCurrentGameTurn()) .. "-" .. tostring(dumpCount)
	local w, h = Map.GetGridSize()
	Emit("BEGIN", {
		"id=" .. dumpID,
		"turn=" .. Game.GetCurrentGameTurn(),
		"player=" .. playerID,
		"w=" .. w,
		"h=" .. h,
	})

	local tileCount = 0
	for i = 0, Map.GetPlotCount() - 1 do
		local plot = Map.GetPlotByIndex(i)
		local x, y = -1, -1
		if plot ~= nil then x, y = plot:GetX(), plot:GetY() end
		if plot ~= nil and vis:IsRevealed(x, y) then
			tileCount = tileCount + 1

			-- Only report resources the player's techs let them see.
			local resIndex = plot:GetResourceType()
			local resource = "NONE"
			if resIndex >= 0 then
				local resRow = GameInfo.Resources[resIndex]
				if resRow ~= nil and Call(playerResources, "IsResourceVisible", resRow.Hash) then
					resource = resRow.ResourceType
				end
			end

			-- Neighbour plot indices in direction order 0..5 (NE, E, SE, SW, W, NW); -1 = off map.
			local neighbours = {}
			for dir = 0, 5 do
				local adj = Map.GetAdjacentPlot(x, y, dir)
				if adj ~= nil then
					table.insert(neighbours, tostring(adj:GetIndex()))
				else
					table.insert(neighbours, "-1")
				end
			end

			local cityID = -1
			local ok, ownerCity = pcall(Cities.GetPlotPurchaseCity, plot)
			if ok and ownerCity ~= nil then cityID = ownerCity:GetID() end

			local fields = {
				"i=" .. i,
				"x=" .. x,
				"y=" .. y,
				"visible=" .. Bool(vis:IsVisible(x, y)),
				"terrain=" .. TypeName(GameInfo.Terrains, plot:GetTerrainType(), "TerrainType"),
				"feature=" .. TypeName(GameInfo.Features, plot:GetFeatureType(), "FeatureType"),
				"resource=" .. resource,
				"resource_count=" .. (resource ~= "NONE" and (Call(plot, "GetResourceCount") or 0) or 0),
				"improvement=" .. TypeName(GameInfo.Improvements, plot:GetImprovementType(), "ImprovementType"),
				"pillaged=" .. Bool(Call(plot, "IsImprovementPillaged")),
				"district=" .. TypeName(GameInfo.Districts, plot:GetDistrictType(), "DistrictType"),
				"wonder=" .. TypeName(GameInfo.Buildings, Call(plot, "GetWonderType") or -1, "BuildingType"),
				"owner=" .. plot:GetOwner(),
				"city=" .. cityID,
				"is_city=" .. Bool(Call(plot, "IsCity")),
				"hills=" .. Bool(Call(plot, "IsHills")),
				"mountain=" .. Bool(Call(plot, "IsMountain")),
				"water=" .. Bool(Call(plot, "IsWater")),
				"lake=" .. Bool(Call(plot, "IsLake")),
				"coastal_land=" .. Bool(Call(plot, "IsCoastalLand")),
				"fresh_water=" .. Bool(Call(plot, "IsFreshWater")),
				"natural_wonder=" .. Bool(Call(plot, "IsNaturalWonder")),
				"impassable=" .. Bool(Call(plot, "IsImpassable")),
				"river=" .. Bool(Call(plot, "IsRiver")),
				-- River/cliff on this plot's W, NW and NE edges; the other three edges
				-- belong to the neighbours, so combine with neighbour data for all six.
				"river_w=" .. Bool(Call(plot, "IsWOfRiver")),
				"river_nw=" .. Bool(Call(plot, "IsNWOfRiver")),
				"river_ne=" .. Bool(Call(plot, "IsNEOfRiver")),
				"cliff_w=" .. Bool(Call(plot, "IsWOfCliff")),
				"cliff_nw=" .. Bool(Call(plot, "IsNWOfCliff")),
				"cliff_ne=" .. Bool(Call(plot, "IsNEOfCliff")),
				"appeal=" .. (Call(plot, "GetAppeal") or 0),
				"continent=" .. TypeName(GameInfo.Continents, Call(plot, "GetContinentType") or -1, "ContinentType"),
				"neighbours=" .. table.concat(neighbours, ","),
			}
			for _, yield in ipairs(yields) do
				table.insert(fields, yield.name .. "=" .. (plot:GetYield(yield.index) or 0))
			end
			Emit("TILE", fields)
		end
	end

	for _, city in player:GetCities():Members() do
		Emit("CITY", {
			"id=" .. city:GetID(),
			"name=" .. Locale.Lookup(city:GetName()),
			"x=" .. city:GetX(),
			"y=" .. city:GetY(),
			"pop=" .. city:GetPopulation(),
		})
	end

	Emit("END", { "id=" .. dumpID, "tiles=" .. tileCount })
	return lines, tileCount
end

-- Builds the dump, prints it (Lua.log, where the platform writes one) and stores it
-- in the game configuration, so the next save contains it. With toClipboard, also
-- copies it to the system clipboard.
function MapDump_SafeDump(toClipboard)
	local ok, result, tileCount = pcall(DumpMap)
	if not ok then
		print(PREFIX .. "ERROR|msg=" .. tostring(result))
		MapDump_SetConfig("MAPDUMP_STATUS", PREFIX .. "ERROR|msg=" .. tostring(result) .. "\n")
		SetStatus("error: " .. tostring(result))
		return
	end
	if result == nil then return end

	for _, line in ipairs(result) do print(line) end
	local text = table.concat(result, "\n") .. "\n"
	local status = tileCount .. " tiles, turn " .. Game.GetCurrentGameTurn()

	local stored, storeErr = MapDump_SetConfig("MAPDUMP_DATA", text)
	MapDump_SetConfig("MAPDUMP_STATUS", PREFIX .. "STATUS|msg=" .. status
		.. (stored and ", stored in config" or (", config failed: " .. tostring(storeErr))) .. "\n")

	if toClipboard then
		local copied, err = pcall(function()
			UIManager:SetClipboardString(text)
		end)
		if copied then
			status = status .. ", copied to clipboard"
		else
			status = status .. ", clipboard failed: " .. tostring(err)
		end
	else
		status = status .. " (Ctrl+Shift+D to copy)"
	end
	SetStatus(status)
end


-- =================================================================================
-- Map tack placement from a plan file
-- =================================================================================
-- ui/mapdump_plan.lua (written by place_tacks.py) defines MapDump_Plan as a list of
-- { x=.., y=.., icon="ICON_DISTRICT_CITY_CENTER", name=".." }. Tacks this mod places
-- carry TACK_PREFIX in their name; only those are ever moved or deleted, so the
-- player's own tacks are left alone.
local TACK_PREFIX = "[MD] "

function MapDump_PlaceTacks()
	MapDump_Plan = nil
	local loaded, loadErr = pcall(function() include("mapdump_plan") end)
	if not loaded or MapDump_Plan == nil then
		local msg = "no plan (" .. tostring(loadErr) .. ")"
		MapDump_SetConfig("MAPDUMP_TACKS", PREFIX .. "TACKS|msg=" .. msg .. "\n")
		return msg
	end

	local playerID = Game.GetLocalPlayer()
	local playerCfg = PlayerConfigurations[playerID]
	if playerCfg == nil then return "no local player" end

	-- Remove our previous tacks and note which tiles hold the player's own.
	local removed, theirs = 0, {}
	for _, pin in pairs(playerCfg:GetMapPins()) do
		local name = pin:GetName() or ""
		if name:sub(1, #TACK_PREFIX) == TACK_PREFIX then
			playerCfg:DeleteMapPin(pin:GetID())
			removed = removed + 1
		else
			theirs[pin:GetHexX() .. "," .. pin:GetHexY()] = true
		end
	end

	local placed, skipped = 0, 0
	for _, tack in ipairs(MapDump_Plan) do
		if theirs[tack.x .. "," .. tack.y] then
			skipped = skipped + 1
		else
			-- GetMapPin creates the pin when the tile has none.
			local pin = playerCfg:GetMapPin(tack.x, tack.y)
			if pin ~= nil then
				pin:SetName(TACK_PREFIX .. (tack.name or ""))
				pin:SetIconName(tack.icon or "ICON_MAP_PIN_CIRCLE")
				placed = placed + 1
			end
		end
	end
	Network.BroadcastPlayerInfo()
	local msg = "placed " .. placed .. ", removed " .. removed .. ", skipped " .. skipped .. " (your own tack there)"
	MapDump_SetConfig("MAPDUMP_TACKS", PREFIX .. "TACKS|msg=" .. msg .. "\n")
	return msg
end

-- Returns a one-line summary of what happened, for showing to the player.
function MapDump_SafePlaceTacks()
	local ok, result = pcall(MapDump_PlaceTacks)
	if not ok then
		MapDump_SetConfig("MAPDUMP_TACKS", PREFIX .. "ERROR|msg=tacks: " .. tostring(result) .. "\n")
		return "error: " .. tostring(result)
	end
	return result
end
