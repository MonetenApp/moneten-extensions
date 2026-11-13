WebBanking {
  version = 1.0,
  url = "https://www.bank.example",
  services = {"Example Bank"},
  description = "Fetches balances and transactions from the made-up Example Bank."
}

local api = "https://api.bank.example/v1"
local connection
local token

local function request(method, path, body, contentType)
  local headers = {Accept = "application/json"}
  if token ~= nil then
    headers["Authorization"] = "Bearer " .. token
  end
  local content = connection:request(method, api .. path, body, contentType, headers)
  return JSON(content):dictionary()
end

local function parseDate(text)
  local year, month, day = text:match("^(%d+)-(%d+)-(%d+)$")
  return os.time{year = tonumber(year), month = tonumber(month), day = tonumber(day), hour = 12}
end

function SupportsBank(protocol, bankCode)
  return protocol == ProtocolWebBanking and bankCode == "Example Bank"
end

function InitializeSession(protocol, bankCode, username, reserved, password)
  connection = Connection()
  local body = "username=" .. MM.urlencode(username) .. "&password=" .. MM.urlencode(password)
  local response = request("POST", "/login", body, "application/x-www-form-urlencoded")
  if response.token == nil then
    return LoginFailed
  end
  token = response.token
end

function ListAccounts(knownAccounts)
  local accounts = {}
  for _, item in ipairs(request("GET", "/accounts").accounts) do
    table.insert(accounts, {
      name = item.name,
      owner = item.owner,
      accountNumber = item.id,
      iban = item.iban,
      bic = item.bic,
      currency = item.currency,
      type = AccountTypeGiro
    })
  end
  return accounts
end

function RefreshAccount(account, since)
  local path = "/accounts/" .. account.accountNumber .. "/transactions?since=" .. os.date("!%Y-%m-%d", since)
  local response = request("GET", path)
  local transactions = {}
  for _, item in ipairs(response.transactions) do
    table.insert(transactions, {
      bookingDate = parseDate(item.date),
      name = item.counterparty,
      purpose = item.purpose,
      amount = item.amount,
      currency = item.currency,
      booked = true
    })
  end
  return {balance = response.balance, transactions = transactions}
end

function EndSession()
  request("POST", "/logout", "", "application/json")
end
