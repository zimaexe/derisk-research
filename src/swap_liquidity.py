import decimal

import requests

import src.blockchain_call
import src.constants


class Prices:
    def __init__(self):
        self.tokens = [
            ("ethereum", "ETH"),
            ("bitcoin", "wBTC"),
            ("usd-coin", "USDC"),
            ("dai", "DAI"),
            ("tether", "USDT"),
        ]
        self.vs_currency = "usd"
        self.prices = {}
        self.get_prices()

    def get_prices(self):
        token_ids = ""
        for token in self.tokens:
            token_ids += f"{token[0]},"
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={token_ids}&vs_currencies={self.vs_currency}"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            for token in self.tokens:
                (id, symbol) = token
                self.prices[symbol] = decimal.Decimal(
                    data[id][self.vs_currency])
        else:
            raise Exception(
                f"Failed getting prices, status code {response.status_code}"
            )

    def get_by_symbol(self, symbol):
        symbol = src.constants.ztoken_to_token(symbol)
        if symbol in self.prices:
            return self.prices[symbol]
        raise Exception(f"Unknown symbol {symbol}")

    def to_dollars(self, n, symbol):
        symbol = src.constants.ztoken_to_token(symbol)
        try:
            price = self.prices[symbol]
            decimals = src.constants.get_decimals(symbol)
        except:
            raise Exception(f"Unknown symbol {symbol}")
        return n / 10**decimals * price

    def to_dollars_pretty(self, n, symbol):
        v = self.to_dollars(n, symbol)
        if abs(v) < 0.00001:
            return "$0"
        return f"${v:.5f}"


class Token:
    def __init__(self, symbol) -> None:
        self.symbol = symbol
        self.address = src.constants.get_address(self.symbol)
        self.decimals = src.constants.get_decimals(self.symbol)
        self.balance_base = None
        self.balance_converted = None


class Pair:
    def tokens_to_id(self, t1, t2):
        (first, second) = tuple(sorted((t1, t2)))
        return f"{first}/{second}"


class Pool(Pair):
    def __init__(self, symbol1, symbol2, address):
        self.id = self.tokens_to_id(symbol1, symbol2)
        self.address = address
        t1 = Token(symbol1)
        t2 = Token(symbol2)
        setattr(self, symbol1, t1)
        setattr(self, symbol2, t2)
        self.tokens = [t1, t2]

    async def get_balance(self):
        for token in self.tokens:
            balance = await src.blockchain_call.balance_of(token.address, self.address)
            token.balance_base = balance
            token.balance_converted = decimal.Decimal(
                balance) / decimal.Decimal(10**token.decimals)

    def update_converted_balance(self):
        for token in self.tokens:
            token.balance_converted = decimal.Decimal(token.balance_base) / decimal.Decimal(
                10**token.decimals
            )

    def buy_tokens(self, symbol, amount):
        # assuming constant product function
        buy = None
        sell = None
        if self.tokens[0].symbol == symbol:
            buy = self.tokens[0]
            sell = self.tokens[1]
        elif self.tokens[1].symbol == symbol:
            buy = self.tokens[1]
            sell = self.tokens[0]
        else:
            raise Exception(f"Could not buy {symbol}")
        const = decimal.Decimal(buy.balance_base) * decimal.Decimal(sell.balance_base)
        new_buy = buy.balance_base - amount
        new_sell = const / decimal.Decimal(new_buy)
        tokens_paid = round(new_sell - sell.balance_base)
        buy.balance_base = new_buy
        sell.balance_base = new_sell
        self.update_converted_balance()
        return tokens_paid

    def supply_at_price(self, symbol: str, initial_price: decimal.Decimal):
        # assuming constant product function
        constant = (
            decimal.Decimal(self.tokens[0].balance_base)
            / (decimal.Decimal("10") ** decimal.Decimal(f"{self.tokens[0].decimals}"))
        ) * (
            decimal.Decimal(self.tokens[1].balance_base)
            / (decimal.Decimal("10") ** decimal.Decimal(f"{self.tokens[1].decimals}"))
        )
        return (initial_price * constant) ** decimal.Decimal("0.5") * (
            decimal.Decimal("1") - decimal.Decimal("0.95") ** decimal.Decimal("0.5")
        )


class SwapAmm(Pair):
    def __init__(self, name):
        self.name = name
        self.pools = {}

    async def get_balance(self):
        for pool in self.pools.values():
            await pool.get_balance()

    def add_pool(self, t1, t2, address):
        pool = Pool(t1, t2, address)
        self.pools[pool.id] = pool

    def get_pool(self, t1, t2):
        try:
            return self.pools[self.tokens_to_id(t1, t2)]
        except:
            raise Exception(
                f"Trying to get pool that is not set: {self.tokens_to_id(t1, t2)}"
            )

    async def total_balance(self, token):
        balance = 0
        t = None
        for pool in self.pools.values():
            for cur_token in pool.tokens:
                if cur_token.symbol == token:
                    balance += token.balance_base
        return balance


async def get_jediswap():
    # Setup the AMM.
    jediswap = SwapAmm("JediSwap")
    jediswap.add_pool(
        "ETH",
        "USDC",
        "0x04d0390b777b424e43839cd1e744799f3de6c176c7e32c1812a41dbd9c19db6a",
    )
    jediswap.add_pool(
        "DAI",
        "ETH",
        "0x07e2a13b40fc1119ec55e0bcf9428eedaa581ab3c924561ad4e955f95da63138",
    )
    jediswap.add_pool(
        "ETH",
        "USDT",
        "0x045e7131d776dddc137e30bdd490b431c7144677e97bf9369f629ed8d3fb7dd6",
    )
    jediswap.add_pool(
        "wBTC",
        "ETH",
        "0x0260e98362e0949fefff8b4de85367c035e44f734c9f8069b6ce2075ae86b45c",
    )
    jediswap.add_pool(
        "wBTC",
        "USDC",
        "0x005a8054e5ca0b277b295a830e53bd71a6a6943b42d0dbb22329437522bc80c8",
    )
    jediswap.add_pool(
        "wBTC",
        "USDT",
        "0x044d13ad98a46fd2322ef2637e5e4c292ce8822f47b7cb9a1d581176a801c1a0",
    )
    jediswap.add_pool(
        "DAI",
        "wBTC",
        "0x039c183c8e5a2df130eefa6fbaa3b8aad89b29891f6272cb0c90deaa93ec6315",
    )
    jediswap.add_pool(
        "DAI",
        "USDC",
        "0x00cfd39f5244f7b617418c018204a8a9f9a7f72e71f0ef38f968eeb2a9ca302b",
    )
    jediswap.add_pool(
        "DAI",
        "USDT",
        "0x00f0f5b3eed258344152e1f17baf84a2e1b621cd754b625bec169e8595aea767",
    )
    jediswap.add_pool(
        "USDC",
        "USDT",
        "0x05801bdad32f343035fb242e98d1e9371ae85bc1543962fedea16c59b35bd19b",
    )
    await jediswap.get_balance()
    return jediswap
