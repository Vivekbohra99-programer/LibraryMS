"""
seed.py – Seed comprehensive, realistic demo data for Library Management System.
Demonstrates all Q17 features (Asset Compression, On-Demand Loading, Purge Tools, Query Caching).
"""
import io
import os
import random
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageDraw, ImageFont

from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.member import Member
from app.models.author import Author
from app.models.category import Category
from app.models.book import Book
from app.models.transaction import Transaction
from app.models.fine import Fine
from app.models.notification import Notification
from app.models.activity_log import ActivityLog
from app.models.setting import Setting
from app.services.compression import compress_text, compress_bytes
from app.services.cache import search_cache


# Palette for cover generation
PALETTES = [
    ((30, 58, 138), (59, 130, 246)),   # Deep blue
    ((17, 94, 89), (20, 184, 166)),    # Teal
    ((76, 29, 149), (139, 92, 246)),  # Purple
    ((136, 19, 55), (244, 63, 94)),   # Crimson
    ((20, 83, 45), (34, 197, 94)),    # Forest green
    ((120, 53, 15), (245, 158, 11)),  # Amber/Bronze
    ((15, 23, 42), (100, 116, 139)),  # Slate
    ((88, 28, 135), (217, 70, 239)),  # Indigo/Magenta
]


def generate_cover_image(title: str, author: str, category: str, width: int = 400, height: int = 600) -> bytes:
    """Generate an attractive book cover image using PIL and return JPEG bytes."""
    palette = random.choice(PALETTES)
    bg_dark, bg_light = palette

    # Create vertical gradient
    base = Image.new('RGB', (width, height), bg_dark)
    top = Image.new('RGB', (width, height), bg_light)
    mask = Image.linear_gradient('L').resize((width, height))
    img = Image.composite(top, base, mask)

    draw = ImageDraw.Draw(img)

    # Decorative header bar
    draw.rectangle([20, 20, width - 20, 28], fill=(255, 255, 255, 180))

    # Category banner
    draw.rounded_rectangle([30, 45, width - 30, 75], radius=6, fill=(0, 0, 0, 80), outline=(255, 255, 255, 100))
    draw.text((45, 52), category.upper(), fill=(255, 255, 255))

    # Center decorative frame
    draw.rectangle([35, 100, width - 35, height - 120], outline=(255, 255, 255, 120), width=2)
    draw.rectangle([42, 107, width - 42, height - 127], outline=(255, 255, 255, 60), width=1)

    # Title lines (word wrap simple)
    words = title.split()
    lines = []
    current_line = []
    for w in words:
        current_line.append(w)
        if len(' '.join(current_line)) > 16:
            lines.append(' '.join(current_line))
            current_line = []
    if current_line:
        lines.append(' '.join(current_line))

    y_start = 180
    for line in lines[:4]:
        draw.text((55, y_start), line, fill=(255, 255, 255))
        y_start += 36

    # Author
    draw.line([55, y_start + 15, width - 55, y_start + 15], fill=(255, 255, 255, 160), width=1)
    draw.text((55, y_start + 30), f"By {author}", fill=(240, 240, 240))

    # Quality badge at bottom
    draw.text((50, height - 80), "LIBRARY EDITION • Q17 OPTIMIZED", fill=(200, 220, 255))
    draw.rectangle([20, height - 28, width - 20, height - 20], fill=(255, 255, 255, 180))

    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=85, optimize=True)
    return buf.getvalue()


SAMPLE_CATALOGUE = [
    # (Title, Author, Category, Publisher, Year, ISBN, BaseDescription)
    (
        "Clean Code: A Handbook of Agile Software Craftsmanship",
        "Robert C. Martin",
        "Software Engineering",
        "Prentice Hall",
        2008,
        "9780132350884",
        "Even bad code can function. But if code isn't clean, it can bring a development organization to its knees. Every year, countless hours and significant resources are lost because of poorly written code. But it doesn't have to be that way. Noted software expert Robert C. Martin presents a revolutionary paradigm with Clean Code. He teams up with his colleagues from Object Mentor to distill the best agile practice of cleaning code on the fly into a handbook that will instill within you the values of a software craftsman and make you a better programmer. Readers will learn the difference between good code and bad code, how to write good code and how to transform bad code into good code, how to create good names, good functions, good objects, and good classes, how to format code for maximum readability, and how to implement complete error handling without obscuring code logic."
    ),
    (
        "The Pragmatic Programmer: Your Journey To Mastery",
        "Andrew Hunt & David Thomas",
        "Software Engineering",
        "Addison-Wesley",
        2019,
        "9780135957059",
        "The Pragmatic Programmer is one of the most influential software development books of all time. Whether you are a new coder, an experienced programmer, or a manager responsible for software projects, these lessons will help you improve your craft. Topics range from personal responsibility and career development to architectural techniques for keeping your code flexible and easy to adapt and reuse. Written as a series of self-contained sections and filled with entertaining anecdotes, thoughtful examples, and interesting analogies, the book illustrates the best approaches and major pitfalls of many different aspects of software development."
    ),
    (
        "Introduction to Algorithms",
        "Thomas H. Cormen",
        "Algorithms",
        "MIT Press",
        2022,
        "9780262046305",
        "Some books on algorithms are rigorous but incomplete; others cover masses of material but lack rigor. Introduction to Algorithms uniquely combines rigor and comprehensiveness. It covers a broad range of algorithms in depth, yet makes their design and analysis accessible to all levels of readers, with self-contained chapters and algorithms in pseudocode. Since the publication of the first edition, it has become the leading algorithms text in universities worldwide as well as the standard reference for professionals."
    ),
    (
        "Design Patterns: Elements of Reusable Object-Oriented Software",
        "Erich Gamma",
        "Software Engineering",
        "Addison-Wesley",
        1994,
        "9780201633610",
        "Capturing a wealth of experience about the design of object-oriented software, four top-notch designers present a catalog of simple and succinct solutions to commonly occurring design problems. Previously undocumented, these 23 patterns allow designers to create more flexible, elegant, and ultimately reusable designs without having to rediscover the design solutions themselves. The authors begin by describing what patterns are and how they help you design object-oriented software. They then go on to systematically name, explain, evaluate, and catalog recurring designs in object-oriented systems."
    ),
    (
        "Database System Concepts",
        "Abraham Silberschatz",
        "Database Systems",
        "McGraw-Hill",
        2019,
        "9780078022159",
        "Database System Concepts presents the fundamental concepts of database management in an intuitive manner geared toward allowing students to begin working with databases as quickly as possible. The text is designed for a first course in databases at the junior/senior undergraduate or first-year graduate level. In addition to fundamental concepts, this text includes practical aspects of database management, application development, and physical architecture."
    ),
    (
        "Operating System Concepts",
        "Abraham Silberschatz",
        "Operating Systems",
        "Wiley",
        2018,
        "9781119456339",
        "Operating System Concepts provides a clear description of the concepts that underlie operating systems. The book does not focus on any particular operating system, but instead provides an overview of operating systems in general. It discusses concepts such as processes, threads, memory management, file systems, I/O systems, protection and security, distributed systems, and real-time systems."
    ),
    (
        "Artificial Intelligence: A Modern Approach",
        "Stuart Russell & Peter Norvig",
        "Artificial Intelligence",
        "Pearson",
        2020,
        "9780134610993",
        "Artificial Intelligence: A Modern Approach offers the most comprehensive, up-to-date introduction to the theory and practice of artificial intelligence. Number one in its field, this textbook is ideal for one or two-semester undergraduate or graduate-level courses in Artificial Intelligence. The authors introduce all major subfields of modern AI: machine learning, probabilistic reasoning, robotics, computer vision, natural language processing, and automated decision-making."
    ),
    (
        "Deep Learning",
        "Ian Goodfellow",
        "Artificial Intelligence",
        "MIT Press",
        2016,
        "9780262035613",
        "Deep learning is a form of machine learning that enables computers to learn from experience and understand the world in terms of a hierarchy of concepts. Because the computer gathers knowledge from experience, there is no need for a human computer operator to formally specify all the knowledge needed. The Deep Learning textbook provides mathematical and conceptual background covering relevant concepts in linear algebra, probability theory, numerical computation, and deep networks."
    ),
    (
        "Computer Networks: A Systems Approach",
        "Andrew S. Tanenbaum",
        "Computer Networks",
        "Pearson",
        2021,
        "9780137523214",
        "Computer Networks describes how networks work from the inside out, starting with physical transmission systems, data link protocols, routing and congestion control, transport protocols like TCP and UDP, and top-layer Internet applications. It provides practical explanations of modern networking protocols including IPv6, wireless networks, 5G cellular communication, content delivery networks, and peer-to-peer systems."
    ),
    (
        "The Mythical Man-Month: Essays on Software Engineering",
        "Fred Brooks",
        "Software Engineering",
        "Addison-Wesley",
        1995,
        "9780201835953",
        "Few books on software project management have been as influential and timeless as The Mythical Man-Month. With a blend of software engineering facts and thought-provoking opinions, Fred Brooks offers insight for anyone managing complex projects. These essays draw from his experience as project manager for the IBM System/360 and then for OS/360, formulating Brooks' Law: adding manpower to a late software project makes it later."
    ),
    (
        "Designing Data-Intensive Applications",
        "Martin Kleppmann",
        "Database Systems",
        "O'Reilly Media",
        2017,
        "9781449373320",
        "Data is at the center of many challenges in system design today. Difficult issues need to be figured out, such as scalability, consistency, reliability, efficiency, and maintainability. In addition, we have an overwhelming variety of tools, including relational databases, NoSQL datastores, stream or batch processors, and message brokers. This book helps navigate this diverse landscape by examining the pros and cons of various technologies for processing and storing data."
    ),
    (
        "Refactoring: Improving the Design of Existing Code",
        "Martin Fowler",
        "Software Engineering",
        "Addison-Wesley",
        2018,
        "9780134757599",
        "For more than twenty years, serious programmers have relied on Martin Fowler's Refactoring to improve the design of existing code and enhance software maintainability, as well as to make existing code easier to understand. This second edition includes an updated catalog of refactorings, demonstrating techniques using modern JavaScript and functional programming principles alongside traditional object-oriented designs."
    ),
    (
        "Structure and Interpretation of Computer Programs",
        "Harold Abelson & Gerald Jay Sussman",
        "Computer Science",
        "MIT Press",
        1996,
        "9780262510875",
        "Structure and Interpretation of Computer Programs has had a dramatic impact on computer science curricula over the past three decades. The book makes use of Lisp to present the principles of programming: procedural abstractions, data abstractions, modularity, state, meta-linguistic abstraction, and compilation, providing deep insights into computer program composition."
    ),
    (
        "Pattern Recognition and Machine Learning",
        "Christopher M. Bishop",
        "Artificial Intelligence",
        "Springer",
        2006,
        "9780387310732",
        "This is the first textbook on pattern recognition to present the Bayesian viewpoint. The book presents approximate inference algorithms that permit fast approximate answers in situations where exact answers are not feasible. It uses graphical models to describe probability distributions when no other books apply graphical models to machine learning."
    ),
    (
        "Compilers: Principles, Techniques, and Tools",
        "Alfred V. Aho",
        "Computer Science",
        "Pearson",
        2006,
        "9780321486813",
        "Known to professors, students, and developers worldwide as the 'Dragon Book,' every chapter has been revised to reflect developments in software engineering, programming languages, and computer architecture that have occurred since 1986. It covers front-end lexical analysis, syntax analysis, syntax-directed translation, runtime environments, intermediate code generation, code optimization, and target code generation."
    ),
    (
        "Modern Operating Systems",
        "Andrew S. Tanenbaum",
        "Operating Systems",
        "Pearson",
        2014,
        "9780133591620",
        "Modern Operating Systems incorporates the latest developments in operating systems technologies. Author Andrew Tanenbaum's clear and entertaining writing style outlines the concepts every operating system designer needs to master. In-depth topic coverage includes processes, threads, memory management, file systems, I/O, deadlocks, virtualization, and multi-core architectures."
    ),
    (
        "Site Reliability Engineering: How Google Runs Production Systems",
        "Betsy Beyer, Chris Jones, Jennifer Petoff, Niall Richard Murphy",
        "Software Engineering",
        "O'Reilly Media",
        2016,
        "9781491929124",
        "Members of the Google SRE team explain how their commitment to the entire lifecycle has enabled Google to successfully build, deploy, monitor, and maintain some of the largest software systems in the world. Learn the principles and practices that enable Google engineers to make systems more scalable, reliable, and efficient."
    ),
    (
        "Python Crash Course: A Hands-On, Project-Based Introduction to Programming",
        "Eric Matthes",
        "Computer Science",
        "No Starch Press",
        2023,
        "9781718502703",
        "Python Crash Course is the world's best-selling guide to the Python programming language. This fast-paced, thorough introduction will have you writing programs, solving problems, and developing working applications in no time. You will learn about basic programming concepts and explore data visualization, web development, and 2D games."
    ),
    (
        "Clean Architecture: A Craftsman's Guide to Software Structure and Design",
        "Robert C. Martin",
        "Software Engineering",
        "Prentice Hall",
        2017,
        "9780134494166",
        "Practical Software Architecture Solutions from the Legendary Robert C. Martin. By applying universal rules of software architecture, you can dramatically improve developer productivity throughout the life of any software system. Uncle Bob presents the direct, essential rules that will help you prevent costly structural mistakes."
    ),
    (
        "Fluent Python: Clear, Concise, and Effective Programming",
        "Luciano Ramalho",
        "Computer Science",
        "O'Reilly Media",
        2022,
        "9781492056355",
        "Don't waste time trying to bend Python to fit patterns you learned in other languages. Python's simplicity lets you become productive quickly, but often this means you aren't using everything it has to offer. With this updated hands-on guide, you'll learn how to write effective, modern Python 3 code by leveraging its best ideas."
    ),
]


def seed_database(reset: bool = True, scale_multiplier: int = 2):
    """Seed the database with complete demo data."""
    app = create_app()

    with app.app_context():
        if reset:
            print("Resetting database schema...")
            db.drop_all()
            db.create_all()

        # 1. System Settings
        print("Seeding default system settings...")
        Setting.seed_defaults()

        # 2. Users & Roles
        print("Seeding default user accounts...")
        admin = User(username='admin', email='admin@library.local', role='admin')
        admin.set_password('admin123')
        db.session.add(admin)

        librarian = User(username='librarian', email='librarian@library.local', role='librarian')
        librarian.set_password('librarian123')
        db.session.add(librarian)

        member_user = User(username='member', email='member@library.local', role='member')
        member_user.set_password('member123')
        db.session.add(member_user)

        # Additional demo members
        extra_members_data = [
            ("alice", "alice@example.com", "Alice Smith", "+1-555-0101", "active", 5),
            ("bob", "bob@example.com", "Bob Johnson", "+1-555-0102", "active", 5),
            ("charlie", "charlie@example.com", "Charlie Davis", "+1-555-0103", "active", 4),
            ("diana", "diana@example.com", "Diana Prince", "+1-555-0104", "active", 6),
            ("edward", "edward@example.com", "Edward Norton", "+1-555-0105", "suspended", 2),
        ]

        member_records = []
        # Main member
        db.session.flush()
        main_member = Member(
            user_id=member_user.id,
            name="Alex Mercer (Standard Member)",
            email="member@library.local",
            phone="+1-555-0100",
            status="active",
            loan_limit=5
        )
        db.session.add(main_member)
        member_records.append(main_member)

        for uname, uemail, mname, uphone, mstatus, mlimit in extra_members_data:
            u = User(username=uname, email=uemail, role='member')
            u.set_password('member123')
            db.session.add(u)
            db.session.flush()
            m = Member(
                user_id=u.id,
                name=mname,
                email=uemail,
                phone=uphone,
                status=mstatus,
                loan_limit=mlimit
            )
            db.session.add(m)
            member_records.append(m)

        db.session.commit()
        print(f"Seeded {len(member_records)} members and associated users.")

        # 3. Authors and Categories
        print("Seeding authors and categories...")
        author_map = {}
        category_map = {}

        # 4. Books with compressed descriptions and covers
        print("Generating catalogue with Q17 Asset Compression...")
        books_created = 0
        all_books = []

        total_catalog = []
        for mult in range(scale_multiplier):
            for item in SAMPLE_CATALOGUE:
                title, author_name, cat_name, publisher, year, isbn_base, desc = item
                if mult > 0:
                    title = f"{title} (Vol. {mult + 1})"
                    isbn = f"{isbn_base[:10]}{mult:03d}"
                else:
                    isbn = isbn_base
                total_catalog.append((title, author_name, cat_name, publisher, year, isbn, desc))

        for title, author_name, cat_name, publisher, year, isbn, desc in total_catalog:
            # Author
            if author_name not in author_map:
                author = Author.query.filter_by(name=author_name).first()
                if not author:
                    author = Author(name=author_name, bio=f"Renowned author and researcher in {cat_name}.")
                    db.session.add(author)
                    db.session.flush()
                author_map[author_name] = author
            author = author_map[author_name]

            # Category
            if cat_name not in category_map:
                category = Category.query.filter_by(name=cat_name).first()
                if not category:
                    category = Category(name=cat_name, description=f"Literature and technical works in {cat_name}.")
                    db.session.add(category)
                    db.session.flush()
                category_map[cat_name] = category
            category = category_map[cat_name]

            # Feature 1: Asset Compression for description (repeat to simulate realistic long text)
            full_description = desc + "\n\n" + (desc * 3)
            desc_raw_size = len(full_description.encode('utf-8'))
            desc_compressed = compress_text(full_description)

            # Feature 1: Asset Compression for cover image
            cover_jpeg = generate_cover_image(title, author_name, cat_name)
            cover_raw_size = len(cover_jpeg)
            cover_compressed = compress_bytes(cover_jpeg)

            quantity = random.randint(3, 8)
            available = quantity

            book = Book(
                title=title,
                isbn=isbn,
                author_id=author.id,
                category_id=category.id,
                publisher=publisher,
                edition="First Edition" if "Vol" not in title else "Revised Edition",
                publication_year=year,
                description_compressed=desc_compressed,
                description_raw_size=desc_raw_size,
                cover_compressed=cover_compressed,
                cover_raw_size=cover_raw_size,
                quantity=quantity,
                available_quantity=available
            )
            db.session.add(book)
            all_books.append(book)
            books_created += 1

        db.session.commit()
        print(f"Seeded {books_created} books with compressed assets.")

        # 5. Transactions & Fines
        print("Seeding transactions, fines, and loans...")
        now = datetime.now(timezone.utc)
        txns_created = 0

        # A: Active normal loans (not overdue)
        for i in range(4):
            b = all_books[i]
            m = member_records[i % len(member_records)]
            b.available_quantity -= 1
            txn = Transaction(
                book_id=b.id,
                member_id=m.id,
                issue_date=now - timedelta(days=5),
                due_date=now + timedelta(days=9),
                status='issued',
                renewal_count=0,
                issued_by=admin.id
            )
            db.session.add(txn)
            txns_created += 1

        # B: Due soon loan (due in 2 days)
        b_due_soon = all_books[4]
        b_due_soon.available_quantity -= 1
        txn_due = Transaction(
            book_id=b_due_soon.id,
            member_id=main_member.id,
            issue_date=now - timedelta(days=12),
            due_date=now + timedelta(days=2),
            status='issued',
            renewal_count=1,
            issued_by=librarian.id
        )
        db.session.add(txn_due)
        txns_created += 1

        # C: Overdue active loans (for fine testing)
        b_overdue = all_books[5]
        b_overdue.available_quantity -= 1
        txn_overdue = Transaction(
            book_id=b_overdue.id,
            member_id=main_member.id,
            issue_date=now - timedelta(days=24),
            due_date=now - timedelta(days=10),
            status='issued',
            renewal_count=0,
            issued_by=admin.id
        )
        db.session.add(txn_overdue)
        txns_created += 1

        # D: Returned transactions (recent, with and without fine)
        for i in range(6, 12):
            b = all_books[i]
            m = member_records[i % len(member_records)]
            ret_date = now - timedelta(days=random.randint(1, 15))
            issue_d = ret_date - timedelta(days=14)
            due_d = issue_d + timedelta(days=14)
            txn = Transaction(
                book_id=b.id,
                member_id=m.id,
                issue_date=issue_d,
                due_date=due_d,
                return_date=ret_date,
                status='returned',
                renewal_count=0,
                issued_by=librarian.id,
                returned_by=librarian.id
            )
            db.session.add(txn)
            txns_created += 1

            # Seed a fine on one returned late
            if i == 6:
                db.session.flush()
                fine = Fine(
                    transaction_id=txn.id,
                    member_id=m.id,
                    amount=15.00,
                    paid=False
                )
                db.session.add(fine)
            elif i == 7:
                db.session.flush()
                fine = Fine(
                    transaction_id=txn.id,
                    member_id=m.id,
                    amount=10.00,
                    paid=True,
                    paid_date=ret_date
                )
                db.session.add(fine)

        # E: Old returned transactions (eligible for DB Purge Tools - Q17 Feature 3)
        print("Seeding old transactions for Q17 purge verification...")
        for i in range(12, 30):
            b = all_books[i % len(all_books)]
            m = member_records[i % len(member_records)]
            days_ago = random.randint(400, 600)
            issue_d = now - timedelta(days=days_ago)
            due_d = issue_d + timedelta(days=14)
            ret_d = due_d + timedelta(days=random.randint(-2, 5))
            old_txn = Transaction(
                book_id=b.id,
                member_id=m.id,
                issue_date=issue_d,
                due_date=due_d,
                return_date=ret_d,
                status='returned',
                renewal_count=0,
                issued_by=admin.id,
                returned_by=admin.id
            )
            db.session.add(old_txn)
            txns_created += 1

        db.session.commit()
        print(f"Seeded {txns_created} transactions (including old returned records for purge).")

        # 6. Notifications
        print("Seeding notifications...")
        n1 = Notification(
            user_id=main_member.user_id,
            message=f"Reminder: '{b_due_soon.title}' is due in 2 days.",
            type='warning',
            link='/transactions'
        )
        n2 = Notification(
            user_id=main_member.user_id,
            message="Welcome to LibraryMS! You can browse the catalogue and borrow up to 5 books.",
            type='info',
            link='/catalogue'
        )
        n3 = Notification(
            user_id=admin.id,
            message="System initialized: Q17 memory optimizations active.",
            type='success',
            link='/admin/performance'
        )
        db.session.add_all([n1, n2, n3])

        # 7. Activity Logs
        print("Seeding activity audit logs...")
        log1 = ActivityLog(user_id=admin.id, action='system_init', details='Database schema and demo dataset initialized', ip_address='127.0.0.1')
        log2 = ActivityLog(user_id=librarian.id, action='book_issue', details=f"Issued '{b_due_soon.title}' to {main_member.name}", ip_address='127.0.0.1')
        log3 = ActivityLog(user_id=main_member.user_id, action='login', details='User member logged in', ip_address='127.0.0.1')
        db.session.add_all([log1, log2, log3])

        db.session.commit()

        # Invalidate LRU Query Cache
        search_cache.invalidate_all()

        print("\n========================================================")
        print("DATABASE SEED COMPLETED SUCCESSFULLY!")
        print("========================================================")
        print("Default accounts created:")
        print("  - Admin:     username: admin     password: admin123")
        print("  - Librarian: username: librarian password: librarian123")
        print("  - Member:    username: member    password: member123")
        print(f"  - Books:        {books_created} books with compressed assets")
        print(f"  - Members:      {len(member_records)}")
        print(f"  - Transactions: {txns_created} (including >365d old returned)")
        print("========================================================\n")


if __name__ == '__main__':
    seed_database()
