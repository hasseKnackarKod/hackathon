# Vi vill typ använda stoploss

# API. Historiska data kan nås direkt
# Samma dag, historisk data men andra aktier

# Förra årets vinnare
#       https://github.com/ErikLundb3rg/LINC-Hackathon-2024/blob/main/README.md 
# Hittade en till om vi vill kika
#       https://github.com/AxelTob/LINC-STEM-Hackathon/tree/master/hackathon_linc

# Pip install hackathon-linc 
import hackathon_linc as lh
import pandas as pd

lh.init('92438482-5598-4e17-8b34-abe17aa8f598')

# These are the Account functions
orders = lh.get_all_orders()
completed = lh.get_completed_orders()
pending = lh.get_pending_orders()
balance = lh.get_balance()
portfolio = lh.get_portfolio()

buy_response = lh.buy('STOCK1', 10) # Default köp på current price. Ganska rimligt att vi vill de?
print('Buy')
# print(buy_response)

# sell_response = lh.sell('STOCK1', 20) # Default sälj på current price. Ganska rimligt att vi vill de?

price_data = pd.DataFrame(lh.get_current_price()['data'])
print(f"Prices:------------\n {price_data}")


# print('Orders')
# print(orders)
# print('Completed')
# print(completed)
# print('Pending')
# print(pending)
print('Balance')
print(balance) 
print('Portfolio')
print(portfolio)

# These are the Order functions

price = lh.get_current_price()
# print('Current price')
# print(price)

historical_data = lh.get_historical_data(365)

# print('Historical data')
# print(pd.DataFrame(historical_data))


# sell_response = lh.sell('STOCK1', 10,200) # Default sälj på current price. Ganska rimligt att vi vill de?
# print('Buy')
# print(buy_response)
# print('Sell')
# print(sell_response)

cancel_response = lh.cancel(order_id='1234', ticker = 'STOCK1')

## Market data functions
tickers = lh.get_all_tickers()
price_data = lh.get_current_price('STOCK1')

print('Tickers')

historical_data = lh.get_historical_data(30, 'STOCK1')


