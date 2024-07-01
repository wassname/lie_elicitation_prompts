# 2024-06-09 16:05:45 

Started project using cookiecutter data science project template.

# 2024-06-15 20:19:22


If this is too hard maybe I should just choose a easier behavior than dishonesty. 
Such as political bias or sycophancy. Or any kind of RLHF ds?


I wonder if I can make a better dataset than truthfulQA? Perhaps using prediction markets, or community notes, or politifact?
- the problem is I'm really honing on misconceptions that are part of general knowledge. So politifact is no good, as are other debunkers. Maybe community notes will be usefull.

Community Notes https://communitynotes.x.com/guide/en/under-the-hood/download-data

> Below, we will describe each column’s data, including the question or source that generated the data, data type, and other relevant information.

but I will also need to scrape tweet id....
https://github.com/colin-fraser/communitynotes
\
need to scrape tweets tpp

# 2024-06-30 10:33:16

OK 2 problems with prev dataset
- my model is only lying 1% of the itme when it understands. There's the risk of thinking a models lying when it's just confused.

I'm using the abliterated model but still 1% lies. Try dolphin?

- even on imbd 10% of questions reliably correct (wth this is easy?)
- 1 % lie, this is low


So, Q: How to modify a model when it show little of the behavior you want to study? Perhaps we can have example of wrong and right?
- I would like honesty, but they are already honest (although they lecture and etc, but that's harder as it's not one token)
- Where it follows instructions and doesn't follow instructions? Even about lying. That could be good

So I can label where it correctly followed instruction and not. We will start of with about 50-50 since the models usually follow instructions. Then we can increase the number of lies.

Is there way we can do it with minimal data, 


Overall I do think pairs are good. We can change some things while keeping others the same. We can even have the llm label diverse examples. And can we backprop over long sequences... well DPO does.

I just think backprop is better than linear methods?

TODO look into DPO


So what about DPO, with RLAIF, but we modify weights instead like circuit breakers? 


Yeah the ideal is:
- the model looks for attributes I want to edit
- it creates an adapter based on modifying the internal representaton in a minimal way, while keeping coherency (perplexity, or perhaps most previous weights)
