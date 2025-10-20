import asyncio

from PipeDSL.utils.utils import json_extractor, to_2d_array, json_extend_extractor, BufferedWriter


def test_json_path():
    json = '{"foo": "bar"}'
    assert json_extractor("foo", json) == "bar"


def test_json_path_arr():
    json = '[{"foo": "bar"}]'
    assert json_extractor("[0].foo", json) == "bar"


example_json = '''
    {
    "id": 38,
    "slug": "DEFAULT_PAYWALL",
    "title": "",
    "text": "",
    "sub_text": "",
    "context_title": "",
    "context_text": "",
    "context_description": "",
    "style": "",
    "assets": {},
    "seconds_left": 0,
    "ends_at": null,
    "tariffs": [
        {
            "id": 14868,
            "title": "1 месяц со скидкой 30%",
            "date_updated": "2025-04-28T07:58:33.277951+00:00",
            "buy_type": "SVOD",
            "status": "activated",
            "partner_sku": "2t4656s85j3pqpvn0242w5a33dqycsnt",
            "inner_sku": "sub_month_1_30percent_main",
            "is_deferred": false,
            "badge_text": "Сохрани цену",
            "highlighted": false,
            "order": 0,
            "url": "https://api.test.tech/gateway/v1/billing/tariffs/14868/",
            "trial": {
                "duration": 7,
                "unit": "days"
            },
            "price": [
                {
                    "currency": "RUB",
                    "excl_tax": "0.00",
                    "incl_tax": "0.00",
                    "excl_tax_excl_discounts": "0.00",
                    "incl_tax_excl_discounts": "0.00",
                    "tax": 0,
                    "is_tax_known": true,
                    "discount": 0,
                    "stockrecord_id": 13145,
                    "period_index": 1,
                    "period_duration": 7,
                    "discount_percent": 30,
                    "period_duration_unit": "days",
                    "period_repeat_count": "1",
                    "price_per_month": 0,
                    "wholesale_discount": 0,
                    "offers": []
                },
                {
                    "currency": "RUB",
                    "excl_tax": "420.00",
                    "incl_tax": "420.00",
                    "excl_tax_excl_discounts": "420.00",
                    "incl_tax_excl_discounts": "420.00",
                    "tax": 0,
                    "is_tax_known": true,
                    "discount": 0,
                    "stockrecord_id": 13146,
                    "period_index": 2,
                    "period_duration": 1,
                    "discount_percent": 0,
                    "period_duration_unit": "months",
                    "period_repeat_count": "infinity",
                    "price_per_month": 420,
                    "wholesale_discount": 0,
                    "offers": []
                }
            ]
        },
        {
            "id": 14934,
            "title": "3 месяца со скидкой 40%",
            "date_updated": "2025-04-28T07:58:33.311114+00:00",
            "buy_type": "SVOD",
            "status": "activated",
            "partner_sku": "r6esbp9dlpekks0j9lheiyj2g4rxa9w2",
            "inner_sku": "sub_month_3_40_per_main",
            "is_deferred": false,
            "badge_text": "",
            "highlighted": false,
            "order": 1,
            "url": "https://api.test.tech/gateway/v1/billing/tariffs/14934/",
            "trial": null,
            "price": [
                {
                    "currency": "RUB",
                    "excl_tax": "899.00",
                    "incl_tax": "899.00",
                    "excl_tax_excl_discounts": "1499.00",
                    "incl_tax_excl_discounts": "1499.00",
                    "tax": 0,
                    "is_tax_known": true,
                    "discount": 600,
                    "stockrecord_id": 13233,
                    "period_index": 1,
                    "period_duration": 3,
                    "discount_percent": 40,
                    "period_duration_unit": "months",
                    "period_repeat_count": "infinity",
                    "price_per_month": 299,
                    "wholesale_discount": 49,
                    "offers": []
                }
            ]
        },
        {
            "id": 14935,
            "title": "6 месяцев со скидкой 40%",
            "date_updated": "2025-04-28T07:58:33.343078+00:00",
            "buy_type": "SVOD",
            "status": "activated",
            "partner_sku": "enatdpiu4d7v8d8eux3tlsgjguabxndm",
            "inner_sku": "sub_month_6_40_per_main",
            "is_deferred": false,
            "badge_text": "",
            "highlighted": false,
            "order": 2,
            "url": "https://api.test.tech/gateway/v1/billing/tariffs/14935/",
            "trial": null,
            "price": [
                {
                    "currency": "RUB",
                    "excl_tax": "1499.00",
                    "incl_tax": "1499.00",
                    "excl_tax_excl_discounts": "2499.00",
                    "incl_tax_excl_discounts": "2499.00",
                    "tax": 0,
                    "is_tax_known": true,
                    "discount": 1000,
                    "stockrecord_id": 13234,
                    "period_index": 1,
                    "period_duration": 6,
                    "discount_percent": 40,
                    "period_duration_unit": "months",
                    "period_repeat_count": "infinity",
                    "price_per_month": 249,
                    "wholesale_discount": 58,
                    "offers": []
                }
            ]
        },
        {
            "id": 14781,
            "title": "12 месяцев со скидкой 50%",
            "date_updated": "2025-04-28T07:58:33.374319+00:00",
            "buy_type": "SVOD",
            "status": "activated",
            "partner_sku": "2751166fc8b541cb983016565c15583a",
            "inner_sku": "sub_year_1_feb2023_main",
            "is_deferred": false,
            "badge_text": "Выгодно",
            "highlighted": false,
            "order": 3,
            "url": "https://api.test.tech/gateway/v1/billing/tariffs/14781/",
            "trial": null,
            "price": [
                {
                    "currency": "RUB",
                    "excl_tax": "2499.00",
                    "incl_tax": "2499.00",
                    "excl_tax_excl_discounts": "4999.00",
                    "incl_tax_excl_discounts": "4999.00",
                    "tax": 0,
                    "is_tax_known": true,
                    "discount": 2500,
                    "stockrecord_id": 13043,
                    "period_index": 1,
                    "period_duration": 12,
                    "discount_percent": 50,
                    "period_duration_unit": "months",
                    "period_repeat_count": "infinity",
                    "price_per_month": 208,
                    "wholesale_discount": 65,
                    "offers": []
                }
            ]
        }
    ]
}
    '''


def test_json_path_arr_1():
    assert json_extend_extractor("tariffs[*].id", example_json) == ["14868", "14934", "14935", "14781"]
    assert json_extend_extractor("$.tariffs[?trial.duration > 0].id", example_json) == ["14868"]


def test_to_2d_array():
    assert list(to_2d_array([[[1]], [[2, 3]]])) == [[1], [2, 3]]


def test_buffered_write():
    total = [1, 2]

    async def main():
        async def write(items: list[int]) -> None:
            nonlocal total
            for i in items:
                total.append(i)

        async def read() -> list[int]:
            nonlocal total
            return total

        writer = BufferedWriter[int](read, write)
        await writer.write(3)
        await writer.write(4)
        await writer.write(5)
        await writer.flush()

    asyncio.run(main())
    assert total == [1, 2, 3, 4, 5]
