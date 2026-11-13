WebBanking {
  version = 1.0,
  url = "https://api.sampleapis.com",
  services = {"Sample Fake Bank"},
  description = "Fetches the made-up card transactions of the SampleAPIs fake bank."
}

local api = "https://api.sampleapis.com/fakebank/accounts"
local connection

function SupportsBank(protocol, bankCode)
  return protocol == ProtocolWebBanking and bankCode == "Sample Fake Bank"
end

function InitializeSession(protocol, bankCode, username, reserved, password)
  connection = Connection()
end

function ListAccounts(knownAccounts)
  return {
    {
      name = "Fake Bank Card",
      accountNumber = "fakebank-1",
      currency = "USD",
      type = AccountTypeCreditCard
    }
  }
end

local function parseDate(text)
  local year, month, day = text:match("^(%d+)-(%d+)-(%d+)$")
  return os.time{year = tonumber(year), month = tonumber(month), day = tonumber(day), hour = 12}
end

function RefreshAccount(account, since)
  local content = connection:request("GET", api .. "?id_lte=12", nil, nil, {Accept = "application/json"})
  local transactions = {}
  local balance = 0
  for _, row in ipairs(JSON(content):dictionary()) do
    local amount = (tonumber(row.credit) or 0) - (tonumber(row.debit) or 0)
    balance = balance + amount
    local bookingDate = parseDate(row.transactionDate)
    if bookingDate >= since then
      table.insert(transactions, {
        bookingDate = bookingDate,
        name = row.description,
        purpose = row.category,
        amount = amount,
        currency = "USD",
        booked = true
      })
    end
  end
  return {balance = balance, transactions = transactions}
end

function EndSession()
end
