#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import urllib
import argparse
import os.path
import re

from html.parser import HTMLParser
from google.cloud import texttospeech
from google.oauth2 import service_account


class ForecastParser(HTMLParser):
    _text = "";
    _lastTag = ""

    def __init__(self):
        super().__init__()
        pass

    def handle_starttag(self, tag, attrs):
        self._lastTag = tag;

    def handle_endtag(self, tag):
        if self._lastTag == "strong":
            self._text += '<break time="0.4s"/>'

        self._lastTag = "";


    def handle_data(self, data):
        if not data:
            return;

        if not self._lastTag:
            return;

        self._text += data;


    def clear(self):
        self._text = ""


class FetchForcast:
    _stateKey = ""

    def __init__(self, state: str, skip_warnings: bool):
        switcher = {
            "Sachsen": "LG",
            "Sachsen-Anhalt": "LH",
            "Thüringen": "LI",
            "Berlin": "PG",
            "Mecklenburg-Vorpommern": "PH",
            "Brandenburg": "PG",
            "Bayern": "MS",
            "Nordbayern": "MO",
            "Sübbayern": "MS",
            "Baden-Würtenberg": "SG",
            "Rheinland-Pfalz": "OI",
            "Nordrhein-Westfalen": "EH",
            "Hessen": "OH",
            "Saarland": "OI",
            "Bremen": "HG",
            "Hamburg": "HH",
            "Niedersachsen": "HG",
            "Schleswig-Holstein": "HH",
        }

        self._stateKey = switcher.get(state, "Nicht unterstütztes Bundesland")
        self._skip_warnings = skip_warnings

    def clean_text(rgx_list, text):
        new_text = text
        for rgx_match in rgx_list:
            new_text = re.sub(rgx_match, '', new_text)
        return new_text

    def fetch_text(self, url):
        resp = urllib.request.urlopen(url)
        s = resp.read().decode('latin-1')
        resp.close()

        parser = ForecastParser()
        parser.feed(s)

        lines = parser._text.splitlines()

        # Meta zeugs rausfiltern
        newLines = [];
        for line in lines:
            line = line.strip()

            if not line:
                continue

            if 'LETZTE AKTUALISIERUNG' in line.upper():
                continue

            if 'WARNRELEVANTE' in line.upper():
#                line = '<!-- ' + line + '-->'
                continue;

            # Sektionen für Wetterwarnungen:
            if ':' in line:

                if (self._skip_warnings):
                    newLines.append('<!-- weather warnings skipped -->\r\n')
                    break

                # Die Überschrift will ich nicht, aber eine Pause
                line = '<!-- ' + line + '-->\r\n<break time="0.5s"/>'

                # folgende Keywords wurden beobachtet:
                #   "STURM / WIND:"
                #   "HITZE:"
                #   "UNWETTER / GEWITTER / STARKREGEN / STURM:"
                #   "FROST:"
                #   "STARKREGEN:"


            # Einheiten ändern
            if 'l/qm' in line:
                line = line.replace('l/qm', 'Liter pro Quadratmeter')

            # Komplexere Nachbearbeitung:
            # rausfiltern von eingeklammerten Windgeschwindigkeiten (Bft 8-10)
            line = re.sub(r"\(Bft\s\d+(-\d+)?\)", "", line)

            # Textfehler / Wortwiederholungen filtern.
            # Beobachtete Beispiele:
            # "Ausbildung einiger Quellwolken. Trocken. Trocken. Maxima zwischen 25 und"
            # https://regex101.com/r/Th8X46/1
            line = re.sub(r"\b([a-zA-Z0-9\.!]+)\s+\1", r"\1", line)

            # längere Wartezeiten bei Kommas:
            line = re.sub(',', ',<break time="0.3s"/>', line)

            # Sprachfehlerkorrektur:
            line = re.sub('Landesteilen', 'Landes-Teilen', line)
            line = re.sub('Landesteile', 'Landes Teile', line)
            line = re.sub('Südost', 'Süd Ost', line)

            # Wortsubstitutionen
            if 'Minima' in line and 'Grad' in line:
                line = re.sub('Minima', 'Tiefsttemperaturen', line)

            if 'Maxima' in line and 'Grad' in line:
                line = re.sub('Maxima', 'Höchsttemperaturen', line)

            newLines.append(line)

        return newLines;

    def fetch(self) -> str:
        parser = ForecastParser()

        allLines = [];
        allLines.append("<speak>\r\n")

        # Gesamtwetterlage
        allLines.append('\r\n<!-- Gesamtwetterlage -->\r\n')
        allLines.append("<p>\r\n")

        lines = self.fetch_text('http://opendata.dwd.de/weather/text_forecasts/html/VHDL54_DW{0}_LATEST_html'.format(self._stateKey));

#        allLines.append('Die Wetterlage:<break time="0.5s"/>\r\n')
        for line in lines:
            allLines.append(line + "\r\n")

        allLines.append("</p>\r\n")

        # Wetter Morgen
        allLines.append('\r\n<!-- Aussichten für heute -->\r\n')
        allLines.append('<break time="1.2s"/>\r\n')
        allLines.append('<s>Die Aussichten für heute.</s><break time="0.4s"/>\r\n')

        allLines.append('<p>\r\n')
        lines = self.fetch_text('http://opendata.dwd.de/weather/text_forecasts/html/VHDL50_DW{0}_LATEST_html'.format(self._stateKey));
        for line in lines:
            allLines.append(line + "\r\n")

        allLines.append("</p>\r\n")

        # Wetter morgen
        allLines.append('\r\n<!-- Aussichten für morgen -->\r\n')
        allLines.append('<break time="1.2s"/>\r\n<p>\r\n')
        allLines.append('<s>Die Aussichten für morgen.</s><break time="0.4s"/>\r\n')

        lines = self.fetch_text('http://opendata.dwd.de/weather/text_forecasts/html/VHDL51_DW{0}_LATEST_html'.format(self._stateKey));
        for line in lines:
            allLines.append(line + "\r\n")

        allLines.append("</p>\r\n")

        allLines.append("</speak>\r\n")

        s = ""
        for line in allLines:
            s += line;

        return s


class TextToSpeech:
    _keyFile = ""
    _useWaveNet = True;

    def __init__(self, keyfile: str, useWaveNet: bool):
        self._keyFile = keyfile
        self._useWaveNet = useWaveNet

    def text_to_speech(self, text, file_name):
        credentials = service_account.Credentials.from_service_account_file(self._keyFile)
        client = texttospeech.TextToSpeechClient(credentials=credentials)

        # Set the text input to be synthesized
        synthesis_input = texttospeech.SynthesisInput(ssml=text)

        if (self._useWaveNet):
            voice = "de-DE-Wavenet-B"
        else:
            voice = "de-DE-Standard-B"

        # Build the voice request, select the language code ("en-US") and the ssml
        # voice gender ("neutral")
        voice = texttospeech.VoiceSelectionParams(
            language_code='de',
            name=voice #,ssml_gender=texttospeech.enums.SsmlVoiceGender.MALE # .MALE
        )

        # Select the type of audio file you want returned
        # https://cloud.google.com/text-to-speech/docs/reference/rest/v1beta1/text/synthesize#VoiceSelectionParams
        audio_config = texttospeech.AudioConfig(
            pitch=-1,
            speaking_rate = 1,
            audio_encoding=texttospeech.AudioEncoding.MP3)

        # Perform the text-to-speech request on the text input with the selected
        # voice parameters and audio file type
        response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)

        # The response's audio_content is binary.
        with open(file_name, 'wb') as out:
            # Write the response to the output file.
            out.write(response.audio_content)
            print('Audio content written to file {0}'.format(file_name))

def main():
    parser = argparse.ArgumentParser(description='wetterbericht kommandozeilenparser.')
    parser.add_argument("-o", "--Output", dest="output",help='Name der Ausgabedatei', type=str, required=False, default='output.mp3')
    parser.add_argument("-s", "--State", dest="state",help='Bundesland', default='Sachsen', choices=[u'Sachsen', u'Sachsen-Anhalt', u'Thüringen', u'Berlin', u'Mecklenburg-Vorpomern', u'Brandenburg', u'Niedersachsen', u'Bremen', u'Hamburg', u'Rheinland-Pfalz', u'Bayern', u'Hessen', u'Saarland', u'Baden-Würtenberg', u'Schleswig-Holstein', u'Nordrhein-Westfalen'])
    parser.add_argument("-k", "--Keyfile", dest="key_file", help='Pfad zu der json Datei mit dem Key für das google text-to-speech api', required=True)
    parser.add_argument("-wave", "--UseWaveNet", dest="use_wave_net", help='Wenn dieses flag gesetzt ist wird sprache hoher qualität ausgegeben.', required=False, default=False, action='store_true')
    parser.add_argument("-nowarn", "--NoWarnings", dest="skip_warnings", help='Ignoriere die Abschnitte zu Warnrelevanten Wettermeldungen.', required=False, default=False, action='store_true')

    args = parser.parse_args()

    if (not os.path.exists(args.key_file)):
        print("Die Schlüsseldatei \"{0}\" kann nicht gefunden werden!".format(args.key_file))
        exit(-1)

    print("\r\n")
    print("Wetterbericht des Deutschen Wetterdienstes als Sprachversion")
    print("------------------------------------------------------------")
    print(" - Python Version: {0}".format(sys.version_info))
    print(' - Schlüsseldatei "{0}" gefunden!'.format(args.key_file))
    print(' - Erstelle Wetterbericht für Bundesland "{0}"'.format(args.state))
    print(' - Erzeugte Ausgabedatei: {0}'.format(args.output))

    if (args.use_wave_net):
        print(' - Verwende WaveNet Stimmen (hohe Qualität)')
    else:
        print(' - Verwende reduzierte Qualität für Sprachausgabe')

    if (args.skip_warnings):
        print(' - Abschnitte zu Warnrelevanten Wetterlagen werden ignoriert')
    else:
        print(' - Kompletter Wetterbericht inklusive warnrelevanter Wetterlagen')

    # Wetterbericht vom DWD abholen
    ff = FetchForcast(args.state, args.skip_warnings)
    ssml = ff.fetch()

    print('\r\nErzeugter Wetterbericht (ssml-Textversion)')
    print('------------------------------------------')
    print(ssml)


    print('\r\nErzeuge Sprachversion...')
    tts = TextToSpeech(args.key_file, args.use_wave_net)
    tts.text_to_speech(ssml, args.output);

# Prerequisites:
# sudo apt-get install python3-setuptools
# pip install --upgrade google-cloud-texttospeech
# pip install --upgrade --user google-cloud-texttospeech

if __name__ == "__main__":
    main()