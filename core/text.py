def plural_form(count, one, few, many):
    """Форма русского существительного после целого числа."""
    if count % 10 == 1 and count % 100 != 11:
        return one
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return few
    return many
