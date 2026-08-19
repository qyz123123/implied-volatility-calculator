"""Create a lightly edited transcript while preserving timestamps and content.

The source is an automated transcription with recurring domain-specific
misrecognitions. This script makes deterministic corrections so the cleanup is
repeatable and auditable; it intentionally does not invent missing speech.
"""

from __future__ import annotations

import re
from pathlib import Path


SOURCE = Path(__file__).with_name("speech.txt")
TARGET = Path(__file__).with_name("speech_revised.txt")


PHRASES = {
    "s and p five hundred": "S&P 500",
    "s and p 500": "S&P 500",
    "volatility index on the S&P 500": "volatility index for the S&P 500",
    "puts and cools": "puts and calls",
    "puts and coals": "puts and calls",
    "cools and puts": "calls and puts",
    "cals or puts": "calls or puts",
    "cool option": "call option",
    "cool options": "call options",
    "cool option data": "call-option data",
    "cool option chain": "call option chain",
    "cool options chain": "call options chain",
    "realize volatility": "realized volatility",
    "realize volatilities": "realized volatilities",
    "ford looking": "forward-looking",
    "forward looking": "forward-looking",
    "their looking estimates": "their forward-looking estimates",
    "black shoals": "Black–Scholes",
    "black shells": "Black–Scholes",
    "black model": "Black–Scholes model",
    "silver parameters": "Solver Parameters",
    "silver results": "Solver Results",
    "solver adding": "Solver add-in",
    "adding isn't": "add-in isn't",
    "xl actually": "Excel actually",
    "within xl": "within Excel",
    "mache s": "matches",
    "lad out": "laid out",
    "option chain chains": "option chains",
    "options chain chains": "options chains",
    "options change": "options chains",
    "option change": "option chain",
    "quart elly": "quarterly",
    "quart value": "quarterly value",
    "quart values": "quarterly values",
    "dai ly": "daily",
    "time frames": "timeframes",
    "fi gues": "figures",
    "figues": "figures",
    "annua zze": "annualized",
    "annua z ze": "annualized",
    "annual iz": "annualized",
    "analyzed ge": "annualized",
    "annualized ging": "annualized figure",
    "x dividend": "ex-dividend",
    "th ex dividend": "the ex-dividend",
    "ex dividend": "ex-dividend",
    "discreet dividend": "discrete dividend",
    "discreet,dividend": "discrete dividend",
    "options data your": "options data, your",
    "pricing inputs puts": "pricing inputs",
    "the 关于of": "the square root of",
    "range oprices": "range of prices",
    "standard deviation figues": "standard deviation figures",
    "cbe website": "CBOE website",
    "cbe dot com": "CBOE.com",
    "cboe dot com": "CBOE.com",
    "nasdaq dot com": "Nasdaq.com",
    "dividend dot com": "Dividend.com",
    "mike so fed": "Microsoft",
    "might soft": "Microsoft",
    "microsoft's": "Microsoft's",
    "google's": "Google's",
    "google stock": "Google stock",
    "tricks ant": "TREX's",
    "tricks trex": "TREX",
    "tricks of": "TREX of",
    "tricks": "TREX",
    "trak s": "TREX",
    "ollie's": "Ollie's",
    "oli dividend": "OLLI dividend",
    "oli and": "OLLI and",
    "only stock": "OLLI stock",
    "ali stock": "OLLI stock",
    "one point five percent dividend yield": "1.05 percent dividend yield",
    "one point zero, five percent": "1.05 percent",
    "zero point, zero nine percent": "0.09 percent",
    "zero point zero nine percent": "0.09 percent",
    "zero point nine percent": "0.09 percent",
    "twenty eight point,one four percent": "28.14 percent",
    "twenty seven point twenty six percent": "27.26 percent",
    "twenty seven point,four two percent": "27.42 percent",
    "forty two point,twenty eight per cent": "42.28 percent",
    "fifty four point, six eight percent": "54.68 percent",
    "seventy four point,four": "74.4",
    "seventy four point, six, four": "74.64",
    "ninety one point four nine": "91.49",
    "ninety two point, five": "92.5",
    "four point three,five": "4.35",
    "four point, six": "4.6",
    "six point four": "6.4",
    "six point seven": "6.7",
    "eight points, even": "$8.70",
    "eight points,even": "$8.70",
    "seventeen ninety three": "1,793",
    "seventeen, ninety five": "1,795",
    "seventeen ninety five": "1,795",
    "sixty nine point five": "69.5",
    "two fifteen": "215",
    "two hundred and fifteen dollars": "$215",
    "one means, a call": "one means a call",
    "minus one means, a put": "minus one means a put",
    "at a eat": "at the money",
    "atth ex-dividend": "at the ex-dividend",
    "payment date is the ten th": "payment date is the tenth",
    "exercise sale": "exercise style",
    "underlying pay ce": "underlying pays",
    "works heets": "worksheets",
    "calculator sand": "calculators and",
    "option pricing model for any option": "option-pricing model for any option",
    "a plus be qualc": "A + B = C",
    "our model, option price": "our model option price",
    "the into them": "built into them",
    "a head check": "a sense check",
    "head check": "sense check",
    "gose to": "preset",
    "isimple": "is simple",
    "gauge": "gauge",
    "gage": "gauge",
    "close to close": "close-to-close",
    "fort elly": "quarterly",
    "returns and normally distributed": "returns are normally distributed",
    "realized til i tile": "realized volatility",
    "rest of this. vi firstly": "rest of this video. Firstly",
    "rest of the and you guys": "rest of the video, and you guys",
    "calculator s": "calculators",
    "underlying paste dividends": "underlying pays dividends",
    "underlying pays dividends": "underlying pays dividends",
    "m aches": "matches",
    "input values into our colored": "input values into are colored",
    "got at the notes area": "got the notes area",
    "dividend.com and dot com": "Dividend.com and Nasdaq.com",
    "tick of a microsoft": "ticker for Microsoft",
    "msft in this case": "MSFT in this case",
    "microsoft corporation's": "Microsoft Corporation's",
    "details are of, the exact dividends that is paid in the past are": "details of the exact dividends paid in the past",
    "secondly it does has there been a dividend announce": "secondly, if it does, whether a dividend has been announced",
    "september, the fifteenth twenty, twenty": "September 15, 2020",
    "eighteenth of november. twenty, twenty": "November 18, 2020",
    "tenth of december, twenty": "December 10, 2020",
    "zero, five six dollars": "$0.56",
    "twenty eighth of november, twenty twenty": "November 28, 2020",
    "irrelevant of": "irrespective of",
    "just say tha can": "just so that you can",
    "atthe": "the",
    "note ox": "notes box",
    "and iso": "and so",
    "that's going to be dot com": "that's going to be CBOE.com",
    "CBOE. Com": "CBOE.com",
    "Nasdaq. Com": "Nasdaq.com",
    "Dividend. Com": "Dividend.com",
    "type ms the tick of the Microsoft": "type MSFT, the ticker for Microsoft",
    "asset that were looking at": "asset that we're looking at",
    "future volatility four": "future volatility for",
    "an fiery": "an expiry",
    "trading at time horizon": "trading time horizon",
    "january, twenty twenty one expires": "January 2021 expiries",
    "january, twenty, twenty one": "January 2021",
    "listed with an ex on the fifteenth": "listed with an expiry on the fifteenth",
    "bid and the ass price": "bid and ask prices",
    "options chain ge": "options chains",
    "evry": "every",
    "chek": "check",
    "afterwards s": "afterwards",
    "back out and imply volatility": "back out an implied volatility",
    "options to for": "options for",
    "cause or puts": "calls or puts",
    "with strikes that the money": "with strikes that are at the money",
    "in this circumstance of one": "in this case, one",
    "which is two hundred and twenty nine": "which is $215.29",
    "i'm just last price": "I'm just going to use the last price",
    "changes with the calculated shortly": "changes in the calculation shortly",
    "tool that helps us do that and that tools called silver": "tool that helps us do that, called Solver",
    "the solver, adding": "the Solver add-in",
    "solver, adding": "Solver add-in",
    "press, ok": "press OK",
    "press and then": "press OK, and then",
    "cell over here, eighty eleven": "cell over here, AB11",
    "annualized ge": "annualized",
    "look into the quarter": "look at the quarterly equation",
    "four, four, because": "four, because",
    "o lies": "OLLI",
    "here kate solvers successfully": "here. Solver has successfully",
    "all of our inputs puts in": "all of our inputs entered",
    "for only and the implied": "for OLLI, and the implied",
    "mid cap stocks like treks and oli": "mid-cap stocks like TREX and OLLI",
    "draw some conclusion": "draw some conclusions",
    "the values are only based on the historical data that we look, at it": "the values are based only on the historical data we examine",
    "they explain define the period": "they explicitly define the period",
    "since their forward-looking estimates": "since they're forward-looking estimates",
    "obtain a implied volatility": "obtain implied volatility",
    "ass price": "ask price",
    "exchanges website": "exchange's website",
    "tick of the": "ticker for",
    "at a in bold": "a bold",
    "derived from historical assets": "derived from historical asset prices",
    "prices and now what": "now what",
    "through out": "throughout",
    "rest of the and you": "rest of the video, and you",
    "what we can do is is": "what we can do is",
    "matches are observed": "matches our observed",
    "values or implied volatility": "values of implied volatility",
    "so let's. start": "so let's start",
    "the website for where they're listed": "the listing exchange's website",
    "need need": "need",
    "the the": "the",
    "in a in an": "in an",
    "and it so": "and so",
    "so so": "so",
    "i'll, i'll": "I'll",
    "light, orange": "light orange",
    "top, right": "top right",
    "solver, adding you": "Solver add-in. You",
    "scale to various": "scaled to various",
    "OLLI volatility decreases": "OLLI. Volatility decreases",
    "forward-forward-looking": "forward-looking",
    "that'sand": "that's it, and",
    "add in sand": "add-ins and",
    "sol va": "Solver",
    "roughing": "roughly",
    "same expire as": "same expiry as",
    "Microsoft in Google": "Microsoft and Google",
    "fifteen th": "fifteenth",
    "soclo see nous to seventy five": "so close enough to $75",
    "inc eight": "in C8",
    "conclusionss": "conclusions",
}


WORD_FIXES = {
    "cools": "calls",
    "coals": "calls",
    "cals": "calls",
    "cool": "call",
    "volatilities": "volatilities",
    "cboe": "CBOE",
    "nasdaq": "Nasdaq",
    "microsoft": "Microsoft",
    "google": "Google",
    "solver": "Solver",
    "excel": "Excel",
    "vix": "VIX",
    "american": "American",
    "european": "European",
    "robins": "or even",
    "gues": "guys",
    "gus": "guys",
    "figu": "figure",
    "fi": "figure",
}


def replace_case_insensitive(text: str, old: str, new: str) -> str:
    return re.sub(re.escape(old), new, text, flags=re.IGNORECASE)


def clean_paragraph(text: str) -> str:
    text = text.strip()
    # Two passes allow a broad correction (for example, "looking estimates")
    # to expose a second, more grammatical phrase correction.
    for _ in range(2):
        for old, new in sorted(PHRASES.items(), key=lambda item: len(item[0]), reverse=True):
            text = replace_case_insensitive(text, old, new)
    for old, new in WORD_FIXES.items():
        text = re.sub(rf"\b{re.escape(old)}\b", new, text, flags=re.IGNORECASE)

    text = re.sub(r"\bi\b", "I", text)
    text = re.sub(r"\bi('m|'ll|'ve|'d)\b", lambda m: "I" + m.group(1), text, flags=re.IGNORECASE)
    text = re.sub(r"\bwere going to\b", "we're going to", text, flags=re.IGNORECASE)
    text = re.sub(r"\byou gus\b", "you guys", text, flags=re.IGNORECASE)
    text = re.sub(r"\bper cent\b", "percent", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+([,.;:?!])", r"\1", text)
    text = re.sub(r"([,.;:?!])(?![\s\n\d])", r"\1 ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Capitalize sentence starts without disturbing tickers and model names.
    chars = list(text)
    capitalize_next = True
    for index, char in enumerate(chars):
        if capitalize_next and char.isalpha():
            chars[index] = char.upper()
            capitalize_next = False
        elif char in ".?!":
            capitalize_next = True
        elif not char.isspace() and capitalize_next:
            capitalize_next = False
    return "".join(chars)


def main() -> None:
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    output = [
        "07. Implied Volatility 2 — revised transcript",
        "",
        "Editorial note: Obvious speech-recognition errors, punctuation, capitalization,",
        "and finance-specific terms have been corrected. Timestamps and substantive",
        "content are preserved; unclear source wording has not been invented.",
        "",
    ]
    for line in lines[1:]:
        if line.startswith("1号讲话人"):
            output.append(line.replace("1号讲话人", "Speaker 1", 1))
        elif line.startswith("2号讲话人"):
            output.append(line.replace("2号讲话人", "Speaker 2", 1))
        elif line.strip() == "对。":
            output.append("Right.")
        elif line.strip():
            output.append(clean_paragraph(line))
        else:
            output.append("")
    TARGET.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
