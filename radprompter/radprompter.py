import os
from tqdm import tqdm
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv

class RadPrompter():
    def __init__(self, client, prompt, output_file, hide_blocks=False, concurrency=1):
        self.client = client
        self.prompt = prompt
        self.hide_blocks = hide_blocks
        self.concurrency = concurrency
        self.output_file = output_file
        assert self.output_file.endswith(".csv"), "Output file must be a .csv file"
        file_exists = os.path.isfile(self.output_file)
        if file_exists:
            print(f"Output file {self.output_file} already exists. Appending to it. If you want to create a new file, please delete the existing file first or pass a new file name.")
        self.log = {
            "Model": self.client.model,
            "Prompt TOML": self.prompt.prompt_file,
            "Prompt Version": self.prompt.version,
            "Prompt Hash": self.prompt.md5_hash,
            "Concurrency Factor": self.concurrency,
        }

        
    def process_single_item(self, item, index):
        prompt = self.prompt.copy()
        prompt.replace_placeholders(item)
            
        messages = [
            {"role": "system", "content": prompt.system_prompt},
        ]
        item_response = []
        for schema in prompt.schemas:
            schema_response = []
            prompt_with_schema = prompt.copy()
            prompt_with_schema.replace_placeholders(schema)
        
            for i in range(prompt.num_turns):
                messages.append({"role": "user", "content": prompt_with_schema.user_prompts[i]})
                if prompt.response_templates[i] != "":
                    messages.append({"role": "assistant", "content": prompt_with_schema.response_templates[i]})
                
                response, messages = self.client.ask_model(messages, prompt_with_schema.stop_tags[i])
                schema_response.append(response)
            
            if len(schema_response) == 1:
                item_response.append({f"{schema['variable_name']}_response":schema_response[0]})
            else:
                for r, schema_response in enumerate(schema_response):    
                    item_response.append({f"{schema['variable_name']}_response_{r}":schema_response[r]})
                    print(f"{schema['variable_name']}_response_{r}")
            
            if self.hide_blocks:
                messages = [
                    {"role": "system", "content": prompt.system_prompt},
                ]
        
        return index, item_response

    def __call__(self, items):
        if not isinstance(items, list):
            items = [items]

        self.log['Start Time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            futures = []
            for index, item in enumerate(items):
                future = executor.submit(self.process_single_item, item, index)
                futures.append(future)

            if self.output_file is not None:
                with open(self.output_file, "a", newline="") as f:
                    writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                    header_written = False

                    for i, future in enumerate(tqdm(as_completed(futures), total=len(futures), desc="Processing items")):
                        index, result = future.result()
                        result.insert(0, {"index": index})
                        result_keys = [list(r.keys())[0] for r in result]
                        for key, value in items[index].items():
                            if key not in result_keys:
                                result.append({key: value})

                        if not header_written:
                            # Write header only if it hasn't been written yet
                            header = [key for r in result for key in r.keys()]
                            writer.writerow(header)
                            header_written = True

                        row = []
                        for r in result:
                            key = list(r.keys())[0]
                            value = r[key]
                            if isinstance(value, list):
                                value = "|".join(str(v) for v in value)
                            row.append(value)
                        writer.writerow(row)

        self.log['End Time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.log['Duration'] = (datetime.strptime(self.log['End Time'], '%Y-%m-%d %H:%M:%S') - 
                                datetime.strptime(self.log['Start Time'], '%Y-%m-%d %H:%M:%S')).total_seconds()
        self.log['Number of Items'] = len(items)
        self.log['Average Processing Time'] = self.log['Duration'] / self.log['Number of Items']                
    
    def save_log(self, log_dir="./RadPrompter.log"):
        with open(log_dir, "w") as f:
            for key, value in self.log.items():
                f.write(f"{key}: {value}\n")
                
            f.write("\n\n")
            f.write("-"*20)
            f.write(" *** - Prompt Content - *** ")
            f.write("-"*20)
            f.write("\n")
            f.write(self.prompt.raw_data)
            
            f.close()