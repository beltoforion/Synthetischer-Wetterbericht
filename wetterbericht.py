#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import urllib
import argparse
import os.path

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

    def __init__(self, state: str):
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

            if 'LETZTE AKTUALISIERUNG' in line.upper():
                continue

            if 'WARNRELEVANTE' in line.upper():
                continue;

            if not line:
                continue

            # Unerwünschte Sektionsüberschriften:
            if 'FROST:' in line:
                # Die Überschrift will ich nicht, aber eine Pause
                line = '<break time="0.5s"/> '

            if 'STARKREGEN:' in line:
                # Die Überschrift will ich nicht, aber eine Pause
                line = '<break time="0.5s"/> '

            # Einheiten ändern
            if 'l/qm' in line:
                line = line.replace('l/qm', 'Liter pro Quadratmeter')

            newLines.append(line)

        return newLines;

    def fetch(self) -> str:
        parser = ForecastParser()

        allLines = [];
        allLines.append("<speak>\r\n")

        # Gesamtwetterlage
        allLines.append("<p>\r\n")

        lines = self.fetch_text('http://opendata.dwd.de/weather/text_forecasts/html/VHDL54_DW{0}_LATEST_html'.format(self._stateKey));
        for line in lines:
            allLines.append(line + "\r\n")

        allLines.append("</p>\r\n")

        # Wetter Morgen
        allLines.append('<break time="0.3s"/>\r\n<p>\r\n')

        lines = self.fetch_text('http://opendata.dwd.de/weather/text_forecasts/html/VHDL50_DW{0}_LATEST_html'.format(self._stateKey));
        for line in lines:
            allLines.append(line + "\r\n")

        allLines.append("</p>\r\n")

        # Wetter Übermorgen
        allLines.append('<break time="0.3s"/>\r\n<p>\r\n')

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
        synthesis_input = texttospeech.types.SynthesisInput(ssml=text)

        if (self._useWaveNet):
            voice = "de-DE-Wavenet-B"
        else:
            voice = "de-DE-Standard-B"

        # Build the voice request, select the language code ("en-US") and the ssml
        # voice gender ("neutral")
        voice = texttospeech.types.VoiceSelectionParams(
            language_code='de',
            name=voice #,ssml_gender=texttospeech.enums.SsmlVoiceGender.MALE
        )

        # Select the type of audio file you want returned
        # https://cloud.google.com/text-to-speech/docs/reference/rest/v1beta1/text/synthesize#VoiceSelectionParams
        audio_config = texttospeech.types.AudioConfig(
            pitch=-1,
            speaking_rate = 1,
            audio_encoding=texttospeech.enums.AudioEncoding.MP3)

        # Perform the text-to-speech request on the text input with the selected
        # voice parameters and audio file type
        response = client.synthesize_speech(synthesis_input, voice, audio_config)

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

    # Wetterbericht vom DWD abholen
    ff = FetchForcast(args.state)
    ssml = ff.fetch()

    print('\r\nErzeugter Wetterbericht (ssml-Textversion)')
    print('------------------------------------------')
    print(ssml)


    print('\r\nErzeuge Sprachversion...')
    tts = TextToSpeech(args.key_file, args.use_wave_net)
    tts.text_to_speech(ssml, args.output);

# Prerequisites:
# pip install --upgrade google-cloud-texttospeech

if __name__ == "__main__":
    main()