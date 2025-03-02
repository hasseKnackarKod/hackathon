top-Loss Sell
                elif symbol in self.portfolio:
                    entry_price = self.portfolio[symbol]['buy_price']
                    quantity = self.portfolio[symbol]['quantity']
                    stop_loss_price = entry_price * (1 - self.std_threshold * prev_STD63 / prev_price)

                    if current_price < stop_loss_price:
                        sell_response = lh.sell(ticker=symbol, amount=quantity)    
                        if 'order_status' in sell_response and sell_response['order_status'] == 'completed': # If successful trade
                            self.cash_capital += quantity * sell_response['price']
                            self.portfolio_value -= quantity * sell_response['price']
                            print(f"S