                "语言：",
                code_block.get(
                    "language",
                    "text",
                )
            )

            print("")

            print(
                code_block.get(
                    "code",
                    "",
                )
            )

    print("")
    print("写在最后：")
    print(
        article.get(
            "ending",
            "",
        )
    )

    print("")
    print("=" * 60)
    print("完整公众号文章打印结束")
    print("=" * 60)

    # --------------------------------------------------------
    # 10. 收集封面候选
    # --------------------------------------------------------

    cover_urls = collect_cover_urls(
        selected_news
    )

    # --------------------------------------------------------
    # 11. 下载真正的 JPEG 封面
    # --------------------------------------------------------

    download_cover(
        cover_urls
    )

    # --------------------------------------------------------
    # 12. 保存 article.json
    # --------------------------------------------------------

    with open(
        ARTICLE_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            article,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("")
    print("=" * 60)
    print("article.json 生成成功")
    print("=" * 60)

    print(
        f"文章标题："
        f"{article['title']}"
    )

    print(
        f"来源："
        f"{article['source']}"
    )

    print(
        f"原文："
        f"{article['original_link']}"
    )

    print(
        f"正文小节："
        f"{len(article['sections'])}"
    )

    total_code_blocks = sum(
        len(
            section.get(
                "code_blocks",
                [],
            )
        )
        for section in article["sections"]
    )

    print(
        f"代码示例："
        f"{total_code_blocks}"
    )

    print("")
    print("=" * 60)
    print("AI 新闻处理完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
