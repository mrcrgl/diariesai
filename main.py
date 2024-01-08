import os
import time
import openai
from dotenv import load_dotenv
from openai import OpenAI
import logging

import instagrapi
import urllib.request
from datetime import datetime
import pathlib
import sys
import argparse

load_dotenv()

logger = logging.getLogger()


def run_command_generate(args):
    initial_post_prompt = args.prompt

    folder_out = "%s/data/%s" % (os.path.curdir, args.date)
    ig_post_file_path = gen_data_ig_post_path(folder_out=folder_out)
    input_file_path = gen_data_input_prompt_path(folder_out=folder_out)

    if os.path.exists(folder_out):
        if os.path.exists(ig_post_file_path):
            print("Post already sent.")
            exit(0)
    else:
        os.mkdir(folder_out)

    if initial_post_prompt is None and os.path.exists(input_file_path):
        f = open(input_file_path, "r")
        initial_post_prompt = f.read()
        f.close()
    else:
        # Generate proper prompt
        if initial_post_prompt is None:
            initial_post_prompt = f"Tagebucheintrag vom %s" % datetime.now().strftime("%d.%m.%Y")

        write_file(file=input_file_path, content=initial_post_prompt)

    print("Input Prompt: ", initial_post_prompt)
    print("Output Dir: ", folder_out)

    generated_post_path = gen_data_generated_post_path(folder_out=folder_out)
    generated_image_path = gen_data_generated_image_path(folder_out=folder_out)

    if not os.path.exists(generated_post_path) or not os.path.exists(generated_image_path):
        generate_content(folder_out=folder_out,
                         initial_post_prompt=initial_post_prompt)
    else:
        print("Skipped content generation.")

    if args.post:
        media_id = publish_to_ig(
            image_path=generated_image_path, caption=read_file(generated_post_path))
        write_file(file=gen_data_ig_post_path(
            folder_out=folder_out), content=media_id)
    else:
        print("Skipped publishing")

    print("done.")


def run_command_prepare(args):
    folder_out = "%s/data/%s" % (os.path.curdir, args.date)
    generated_post_path = gen_data_generated_post_path(folder_out=folder_out)
    ig_post_file_path = gen_data_ig_post_path(folder_out=folder_out)
    input_file_path = gen_data_input_prompt_path(folder_out=folder_out)

    if os.path.exists(generated_post_path):
        print("Skipped. Post already generated.")
        exit(0)

    if os.path.exists(ig_post_file_path):
        print("Skipped. Post already sent.")
        exit(0)

    if not os.path.exists(folder_out):
        os.mkdir(folder_out)

    write_file(file=input_file_path,
               content=f"Tagebucheintrag vom {args.date}: {args.prompt}")

    print("saved.")


def main():
    args = parser.parse_args(sys.argv[1:])
    args.func(args)
    exit(0)


def gen_data_path(folder_out: str, filename: str) -> str:
    return f"{folder_out}/{filename}"


def gen_data_input_prompt_path(folder_out: str) -> str:
    return gen_data_path(folder_out=folder_out, filename="input.txt")


def gen_data_generated_image_path(folder_out: str) -> str:
    return gen_data_path(folder_out=folder_out, filename="generated_image.png")


def gen_data_ig_post_path(folder_out: str) -> str:
    return gen_data_path(folder_out=folder_out, filename="ig_post_id.txt")


def gen_data_generated_post_path(folder_out: str) -> str:
    return gen_data_path(folder_out=folder_out, filename="generated_post.txt")


def gen_data_generated_image_prompt_path(folder_out: str) -> str:
    return gen_data_path(folder_out=folder_out, filename="generated_image_prompt.txt")


def generate_content(folder_out: str, initial_post_prompt: str) -> (str, str):
    assistant_id = os.environ.get("OPENAI_ASSISTANT_ID")
    organization = os.environ.get("OPENAI_ORGANISATION")

    client = OpenAI(
        organization=organization,
        api_key=os.environ.get("OPENAI_API_KEY")
    )

    update_assistant(assistant_id=assistant_id, client=client)

    thread = client.beta.threads.create(
        messages=[dict(role="user", content=initial_post_prompt)]
    )

    run_and_wait(job_desc="Generate Post", client=client,
                 assistant_id=assistant_id, thread_id=thread.id)

    generated_post = read_response(client=client, thread_id=thread.id)
    write_file(file=gen_data_generated_post_path(
        folder_out=folder_out), content=generated_post)

    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content="Erstelle einen detaillierten Prompt für ein fotorealistisches Bild dieser szene"
    )

    run_and_wait(job_desc="Generate Image Prompt", client=client,
                 assistant_id=assistant_id, thread_id=thread.id)

    generated_image_prompt = read_response(client=client, thread_id=thread.id)
    write_file(file=gen_data_generated_image_prompt_path(
        folder_out=folder_out), content=generated_image_prompt)

    print("Generate Image")
    output = client.images.generate(
        model='dall-e-3', prompt=generated_image_prompt, size="1024x1024", n=1)

    generated_image_path = gen_data_generated_image_path(folder_out=folder_out)
    urllib.request.urlretrieve(output.data[0].url, generated_image_path)
    return generated_post, generated_image_path


def write_file(file: str, content: str) -> str:
    f = open(file, 'w')
    f.write(content)
    f.flush()
    f.close()

    return file


def read_instructions_file() -> str:
    return read_file("instructions.txt")


def read_file(file: str) -> str:
    fd = open(file, "r")
    content = fd.read()
    fd.close()
    return content


def update_assistant(client: openai.Client, assistant_id: str):
    client.beta.assistants.update(
        assistant_id=assistant_id,
        instructions=read_instructions_file(),
        model="gpt-4-1106-preview"
    )


def run_and_wait(job_desc: str, client: openai.Client, assistant_id: str, thread_id: str):
    print(job_desc, end="")
    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id
    )

    while True:
        time.sleep(1)
        runs = client.beta.threads.runs.list(thread_id=thread_id)
        ok = True
        for run in runs.data:
            if run.status == "in_progress":
                print(".", end="")
                ok = False

        if ok:
            print("done")
            break


def read_response(client: openai.Client, thread_id: str) -> str:
    messages = client.beta.threads.messages.list(
        thread_id=thread_id,
        limit=5
    )

    return messages.data[0].content[0].text.value


def publish_to_ig(image_path: str, caption: str) -> str:
    settings = pathlib.Path("insta_settings.json")

    print("Login to IG")
    cl = instagrapi.Client()
    if os.path.exists(settings):
        cl.load_settings(settings)

    cl.set_locale("de_DE")
    cl.init()
    cl.login(os.environ.get("IG_USER"), os.environ.get("IG_PASS"))
    cl.dump_settings(settings)

    print("Post to IG")
    out = cl.photo_upload(
        path=pathlib.Path(image_path),
        caption=caption
    )

    return out.id


parser = argparse.ArgumentParser(
    prog="diaries_ai", description='Create daily diary for ig.')
subcommands = parser.add_subparsers(required=True)
generate_command = subcommands.add_parser("generate")
generate_command.add_argument('--prompt', help='prompt to use')
generate_command.add_argument('--date', help='date of post in YYYY-MM-DD format. Defaults today',
                              default=datetime.now().strftime("%Y-%m-%d"))
generate_command.add_argument('--post', help='post to ig', action="store_true")
generate_command.set_defaults(func=run_command_generate)

prepare_command = subcommands.add_parser("prepare")
prepare_command.add_argument('--prompt', help='prompt to use', required=True)
prepare_command.add_argument('--date', help='date of post in YYYY-MM-DD format. Defaults today',
                             default=datetime.now().strftime("%Y-%m-%d"))
prepare_command.set_defaults(func=run_command_prepare)


if __name__ == "__main__":
    main()
